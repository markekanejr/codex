from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from workforce.forms import (
    InvitationAcceptForm,
    PlanForm,
    RoutineForm,
    SegmentForm,
    SourceForm,
    TripForm,
)
from workforce.models import (
    Delivery,
    Invitation,
    Membership,
    PlanItem,
    Routine,
    SourceRecord,
    Trip,
    TripSegment,
)
from workforce.services.access import editable, membership, scoped
from workforce.services.invitations import accept_invitation, issue_invitation, token_hash


@login_required
def today(request):
    if not Membership.objects.filter(user=request.user).exists():
        return render(request, "workforce/today.html", {"needs_household": True})
    member = membership(request.user)
    return render(
        request,
        "workforce/today.html",
        {
            "household": member.household,
            "plans": scoped(PlanItem, request.user)
            .exclude(status__in=["done", "canceled"])
            .order_by("start_at", "due_at")[:12],
            "trips": scoped(Trip, request.user).exclude(status="canceled")[:4],
        },
    )


@login_required
def plans(request):
    return render(
        request,
        "workforce/plans.html",
        {
            "plans": scoped(PlanItem, request.user).order_by("start_at"),
            "routines": scoped(Routine, request.user),
            "sources": scoped(SourceRecord, request.user),
        },
    )


def edit_owned(request, model, form_class, name, pk=None):
    member = membership(request.user)
    with transaction.atomic():
        instance = (
            editable(model, request.user, pk)
            if pk
            else model(household=member.household, owner=request.user)
        )
        if pk:
            instance = model.objects.select_for_update().get(pk=instance.pk)
        form = form_class(request.POST or None, instance=instance, user=request.user)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, f"{name} saved.")
            return redirect("trips" if model is Trip else "plans")
    return render(
        request,
        "workforce/form.html",
        {"form": form, "heading": f"{'Edit' if pk else 'Add'} {name}"},
    )


@login_required
def plan_edit(request, pk=None):
    return edit_owned(request, PlanItem, PlanForm, "plan", pk)


@login_required
def routine_edit(request, pk=None):
    return edit_owned(request, Routine, RoutineForm, "routine", pk)


@login_required
def source_edit(request, pk=None):
    return edit_owned(request, SourceRecord, SourceForm, "source", pk)


@login_required
def trips(request):
    return render(request, "workforce/trips.html", {"trips": scoped(Trip, request.user)})


@login_required
def trip_edit(request, pk=None):
    return edit_owned(request, Trip, TripForm, "trip", pk)


@login_required
def trip_detail(request, pk):
    trip = get_object_or_404(scoped(Trip, request.user), pk=pk)
    return render(request, "workforce/trip.html", {"trip": trip, "segments": trip.segments.all()})


@login_required
def segment_edit(request, trip_pk, pk=None):
    with transaction.atomic():
        trip = editable(Trip, request.user, trip_pk)
        instance = (
            get_object_or_404(TripSegment.objects.select_for_update(), trip=trip, pk=pk)
            if pk
            else TripSegment(trip=trip)
        )
        form = SegmentForm(request.POST or None, user=request.user, instance=instance)
        if request.method == "POST" and form.is_valid():
            form.save()
            trip.save()
            return redirect("trip_detail", pk=trip.pk)
    return render(
        request, "workforce/form.html", {"form": form, "heading": "Flight or hotel details"}
    )


@login_required
def export_plans(request):
    return JsonResponse(
        {
            "plans": list(
                scoped(PlanItem, request.user).values(
                    "id", "title", "audience", "status", "start_at", "end_at", "due_at", "timezone"
                )
            )
        }
    )


def invitation_accept(request, token):
    invitation = get_object_or_404(
        Invitation,
        token_hash=token_hash(token),
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    form = InvitationAcceptForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = accept_invitation(token, form.cleaned_data["password"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            login(request, user)
            return redirect("today")
    return render(
        request,
        "workforce/form.html",
        {"form": form, "heading": "Join your household", "description": invitation.email},
    )


@login_required
def household_settings(request):
    member = membership(request.user)
    invite_url = None
    if request.method == "POST":
        if request.POST.get("operation") == "invite" and member.role == "owner":
            from django.core.validators import validate_email

            try:
                validate_email(request.POST.get("email", ""))
                _, token = issue_invitation(member.household, request.POST["email"])
                invite_url = request.build_absolute_uri(reverse("invitation_accept", args=[token]))
            except ValidationError:
                messages.error(request, "Enter a valid email address.")
        elif request.POST.get("operation") == "pause":
            member.household.pause_outbound = not member.household.pause_outbound
            member.household.save(update_fields=["pause_outbound"])
            return redirect("household_settings")
    return render(request, "workforce/settings.html", {"member": member, "invite_url": invite_url})


def health(request):
    return HttpResponse("ok", content_type="text/plain")


@login_required
def review(request):
    from workforce.models import ActionProposal

    return render(
        request,
        "workforce/review.html",
        {"proposals": scoped(ActionProposal, request.user).order_by("-id")},
    )


@login_required
def action_edit(request, pk=None):
    from workforce.forms import ActionForm
    from workforce.models import ActionProposal

    member = membership(request.user)
    with transaction.atomic():
        instance = (
            editable(ActionProposal, request.user, pk)
            if pk
            else ActionProposal(
                household=member.household, owner=request.user, affected_person=request.user
            )
        )
        if pk:
            instance = ActionProposal.objects.select_for_update().get(pk=pk)
            if instance.status in ("executing", "succeeded", "outcome_unknown"):
                messages.error(request, "Submitted actions cannot be edited.")
                return redirect("action_detail", pk=pk)
        form = ActionForm(request.POST or None, instance=instance, user=request.user)
        if request.method == "POST" and form.is_valid():
            proposal = form.save(commit=False)
            proposal.status, proposal.ready_by = "draft", ""
            proposal.save()
            return redirect("action_detail", pk=proposal.pk)
    return render(
        request,
        "workforce/form.html",
        {
            "form": form,
            "heading": "Reviewable action proposal",
            "description": "This build only simulates actions. No vendor will be contacted.",
        },
    )


@login_required
def action_detail(request, pk):
    from workforce.models import ActionProposal
    from workforce.services.spending import evaluate

    proposal = get_object_or_404(scoped(ActionProposal, request.user), pk=pk)
    decision, reason = evaluate(proposal)
    return render(
        request,
        "workforce/action.html",
        {
            "proposal": proposal,
            "reason": reason,
            "decision": decision,
            "can_approve": membership(request.user).pricing_approver,
            "total": None if proposal.total_cents is None else f"{proposal.total_cents / 100:.2f}",
        },
    )


@login_required
@require_POST
def action_decide(request, pk):
    from workforce.models import ActionProposal
    from workforce.services import actions

    proposal = get_object_or_404(scoped(ActionProposal, request.user), pk=pk)
    try:
        operation = request.POST.get("operation")
        if operation == "submit":
            actions.submit(request.user, pk)
        elif operation == "approve":
            actions.approve(request.user, pk, int(request.POST.get("revision", "0")))
        elif operation == "reject":
            actions.reject(request.user, pk)
        elif operation == "queue":
            actions.queue(request.user, pk)
        else:
            raise ValidationError("Choose a valid action.")
    except (ValidationError, ValueError) as error:
        messages.error(
            request,
            "; ".join(error.messages)
            if isinstance(error, ValidationError)
            else "Invalid revision.",
        )
    return redirect("action_detail", pk=proposal.pk)


@login_required
def budget_settings(request):
    from workforce.forms import BudgetForm, CommitmentForm, PolicyForm
    from workforce.models import BudgetCommitment, BudgetConfig, WorkflowPolicy
    from workforce.services.budgets import summary

    member = membership(request.user)
    budget, _ = BudgetConfig.objects.get_or_create(household=member.household)
    form = BudgetForm(
        initial={
            "monthly_limit": budget.monthly_limit_cents / 100,
            "variable_limit": budget.variable_limit_cents / 100,
            "auto_limit": member.household.auto_limit_cents / 100,
            "costs_confirmed": budget.costs_confirmed,
        }
    )
    commitment_form, policy_form = CommitmentForm(), PolicyForm()
    if request.method == "POST":
        operation = request.POST.get("operation")
        if (
            operation in ("budget", "commitment", "remove_commitment")
            and not member.pricing_approver
        ):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Only the pricing approver can configure costs.")
        if operation == "budget":
            form = BudgetForm(request.POST)
            if form.is_valid():
                with transaction.atomic():
                    budget = BudgetConfig.objects.select_for_update().get(pk=budget.pk)
                    budget.monthly_limit_cents = int(form.cleaned_data["monthly_limit"] * 100)
                    budget.variable_limit_cents = int(form.cleaned_data["variable_limit"] * 100)
                    budget.costs_confirmed = form.cleaned_data["costs_confirmed"]
                    budget.save()
                    member.household.auto_limit_cents = int(form.cleaned_data["auto_limit"] * 100)
                    member.household.save(update_fields=["auto_limit_cents"])
                return redirect("budget_settings")
        elif operation == "commitment":
            commitment_form = CommitmentForm(request.POST)
            if commitment_form.is_valid():
                value = commitment_form.cleaned_data["monthly_cost"]
                with transaction.atomic():
                    BudgetConfig.objects.select_for_update().get(pk=budget.pk)
                    BudgetCommitment.objects.create(
                        budget=budget,
                        label=commitment_form.cleaned_data["label"],
                        monthly_cents=None if value is None else int(value * 100),
                    )
                return redirect("budget_settings")
        elif operation == "remove_commitment":
            with transaction.atomic():
                BudgetConfig.objects.select_for_update().get(pk=budget.pk)
                get_object_or_404(
                    BudgetCommitment, pk=request.POST.get("id"), budget=budget
                ).delete()
            return redirect("budget_settings")
        elif operation == "policy":
            policy_form = PolicyForm(request.POST)
            if policy_form.is_valid():
                WorkflowPolicy.objects.update_or_create(
                    household=member.household,
                    owner=request.user,
                    workflow=policy_form.cleaned_data["workflow"],
                    vendor=policy_form.cleaned_data["vendor"],
                    defaults={"enabled": policy_form.cleaned_data["enabled"]},
                )
                return redirect("budget_settings")
    totals = summary(budget)
    return render(
        request,
        "workforce/budget.html",
        {
            "member": member,
            "form": form,
            "commitment_form": commitment_form,
            "policy_form": policy_form,
            "commitments": budget.commitments.all(),
            "known": totals["known"],
            "remaining": f"{totals['remaining'] / 100:.2f}",
            "policies": WorkflowPolicy.objects.filter(
                household=member.household, owner=request.user
            ),
        },
    )


@login_required
def briefing(request):
    from workforce.services.briefings import build_briefing, refs_valid

    member = membership(request.user)
    principal = (
        "shared" if request.GET.get("scope", "shared") == "shared" else f"user:{request.user.pk}"
    )
    content, _ = build_briefing(member.household, principal, timezone.localdate())
    history = list(
        Delivery.objects.filter(household=member.household, recipient=request.user).order_by(
            "-created_at"
        )[:20]
    )
    for delivery in history:
        if not refs_valid(member.household_id, delivery.principal, delivery.refs):
            delivery.content = (
                "This preview is out of date. Its source records changed or became private."
            )
    return render(
        request,
        "workforce/briefing.html",
        {
            "content": content,
            "history": history,
            "scope": "shared" if principal == "shared" else "private",
        },
    )
