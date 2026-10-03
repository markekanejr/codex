from datetime import date
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from workforce.models import BudgetConfig, UsageEvent, UsageReservation


class BudgetUnavailable(ValidationError):
    pass


def month_for(household, now=None):
    day = (now or timezone.now()).astimezone(ZoneInfo(household.timezone)).date()
    return date(day.year, day.month, 1)


def summary(budget, month=None):
    month = month or month_for(budget.household)
    commitments = list(budget.commitments.all())
    known = budget.costs_confirmed and all(item.monthly_cents is not None for item in commitments)
    fixed = sum(item.monthly_cents or 0 for item in commitments)
    reservations = UsageReservation.objects.filter(budget=budget, billing_month=month)
    reserved = (
        reservations.filter(status="reserved").aggregate(total=Sum("estimate_cents"))["total"] or 0
    )
    spent = reservations.filter(status="settled").aggregate(total=Sum("actual_cents"))["total"] or 0
    allowance = min(budget.variable_limit_cents, max(0, budget.monthly_limit_cents - fixed))
    return {
        "known": known,
        "fixed": fixed,
        "reserved": reserved,
        "spent": spent,
        "remaining": max(0, allowance - reserved - spent),
    }


@transaction.atomic
def reserve(household, estimate_cents, key, now=None):
    if type(estimate_cents) is not int or estimate_cents < 0:
        raise BudgetUnavailable("A non-negative integer cost estimate is required.")
    budget = BudgetConfig.objects.select_for_update().get(household=household)
    existing = UsageReservation.objects.filter(key=key).first()
    if existing:
        if existing.budget_id != budget.pk or existing.estimate_cents != estimate_cents:
            raise BudgetUnavailable("Reservation key does not match this request.")
        return existing
    if budget.household.pause_ai:
        raise BudgetUnavailable("Paid AI is paused.")
    month = month_for(household, now)
    totals = summary(budget, month)
    if not totals["known"]:
        raise BudgetUnavailable("Existing subscription costs have not all been confirmed.")
    if estimate_cents > totals["remaining"]:
        raise BudgetUnavailable("This request exceeds the remaining service allowance.")
    return UsageReservation.objects.create(
        budget=budget, billing_month=month, key=key, estimate_cents=estimate_cents
    )


@transaction.atomic
def settle(reservation, actual_cents=None, cancel=False):
    BudgetConfig.objects.select_for_update().get(pk=reservation.budget_id)
    record = UsageReservation.objects.select_for_update().get(pk=reservation.pk)
    if record.status != "reserved":
        return record
    if cancel:
        record.status = "canceled"
        record.save(update_fields=["status"])
        return record
    actual = record.estimate_cents if actual_cents is None else actual_cents
    if type(actual) is not int or actual < 0:
        raise BudgetUnavailable("Actual cost must be a non-negative integer.")
    record.status, record.actual_cents = "settled", actual
    record.save(update_fields=["status", "actual_cents"])
    UsageEvent.objects.create(
        reservation=record, amount_cents=actual, estimated=actual_cents is None
    )
    return record
