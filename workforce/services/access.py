from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.shortcuts import get_object_or_404

from workforce.models import Membership, PlanItem


def membership(user):
    return get_object_or_404(Membership.objects.select_related("household"), user=user)


def scoped(model, user):
    member = membership(user)
    records = model.objects.filter(household=member.household).filter(
        Q(audience="shared") | Q(owner=user)
    )
    if model is PlanItem:
        records = records.filter(
            Q(source__isnull=True)
            | (
                Q(source__household_id=F("household_id"))
                & (
                    Q(source__audience="shared")
                    | Q(source__owner=user, audience="private", owner=user)
                )
            )
        )
    return records


def editable(model, user, pk):
    return get_object_or_404(scoped(model, user).filter(owner=user), pk=pk)


def audience_scope(model, household_id, principal):
    records = model.objects.filter(household_id=household_id)
    if principal == "shared":
        return records.filter(audience="shared")
    user_id = int(principal.removeprefix("user:"))
    if not Membership.objects.filter(household_id=household_id, user_id=user_id).exists():
        raise PermissionDenied("No membership for this audience.")
    return records.filter(audience="private", owner_id=user_id)


def source_visible(item, principal):
    source = item.source
    return not source or (
        source.household_id == item.household_id
        and (source.audience == "shared" or principal == f"user:{source.owner_id}")
    )
