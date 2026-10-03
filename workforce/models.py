import uuid
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import localdate


class User(AbstractUser):
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class Household(models.Model):
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=80, default="America/Chicago")
    briefing_time = models.TimeField(default=time(7, 30))
    pause_outbound = models.BooleanField(default=False)
    pause_ai = models.BooleanField(default=True)
    auto_limit_cents = models.PositiveIntegerField(default=10000)


class Membership(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[("owner", "Owner"), ("partner", "Partner")])
    pricing_approver = models.BooleanField(default=False)
    notifications = models.BooleanField(default=True)


class Invitation(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)


class OwnedRecord(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    audience = models.CharField(
        max_length=10,
        choices=[("shared", "Shared household"), ("private", "Only me")],
        default="private",
    )
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=Q(audience__in=["shared", "private"]), name="%(class)s_audience_valid"
            )
        ]

    def clean(self):
        super().clean()
        if self.owner_id and self.household_id:
            if not Membership.objects.filter(
                user_id=self.owner_id, household_id=self.household_id
            ).exists():
                raise ValidationError("The owner must belong to this household.")

    def save(self, *args, **kwargs):
        if self.pk:
            self.revision += 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"revision"}
        super().save(*args, **kwargs)


class SourceRecord(OwnedRecord):
    title = models.CharField(max_length=200)
    external_id = models.CharField(max_length=200, blank=True)
    provenance = models.CharField(
        max_length=20,
        choices=[("user_reported", "User reported"), ("confirmed", "User confirmed")],
        default="user_reported",
    )
    observed_at = models.DateTimeField(default=timezone.now)
    data = models.TextField(max_length=10000, blank=True)


def validate_zone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Choose a valid IANA timezone, such as America/Chicago.") from None


class PlanItem(OwnedRecord):
    title = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=20,
        choices=[("event", "Event"), ("task", "Task"), ("reminder", "Reminder"), ("note", "Note")],
        default="event",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("proposed", "Proposed"),
            ("confirmed", "Confirmed"),
            ("done", "Done"),
            ("canceled", "Canceled"),
        ],
        default="proposed",
    )
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(
        max_length=80, default="America/Chicago", validators=[validate_zone]
    )
    source = models.ForeignKey(SourceRecord, null=True, blank=True, on_delete=models.SET_NULL)

    def clean(self):
        super().clean()
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError("The end must be after the start.")
        if self.source_id:
            source = self.source
            if source.household_id != self.household_id:
                raise ValidationError("Source belongs to another household.")
            if source.audience == "private" and (
                self.audience == "shared" or source.owner_id != self.owner_id
            ):
                raise ValidationError("A private source cannot be linked to a shared record.")


class Routine(OwnedRecord):
    title = models.CharField(max_length=200)
    local_time = models.TimeField()
    timezone = models.CharField(
        max_length=80, default="America/Chicago", validators=[validate_zone]
    )
    rule = models.CharField(max_length=10, choices=[("daily", "Daily"), ("weekly", "Weekly")])
    weekdays = models.JSONField(default=list, blank=True)
    active_from = models.DateField(default=localdate)
    active_until = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if not isinstance(self.weekdays, list) or any(
            type(day) is not int or day not in range(7) for day in self.weekdays
        ):
            raise ValidationError("Weekdays must be integers from 0 to 6.")
        if self.rule == "weekly" and not self.weekdays:
            raise ValidationError("Choose at least one weekday.")
        if self.active_until and self.active_until < self.active_from:
            raise ValidationError("The end date must follow the start date.")


class Trip(OwnedRecord):
    title = models.CharField(max_length=200)
    departure_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("planning", "Planning"),
            ("booked", "Bookings reported"),
            ("confirmed", "Itinerary confirmed"),
            ("canceled", "Canceled"),
        ],
        default="planning",
    )
    airport_buffer_minutes = models.PositiveIntegerField(null=True, blank=True)
    ground_minutes = models.PositiveIntegerField(null=True, blank=True)

    @property
    def missing_details(self):
        missing = []
        flights = self.segments.filter(kind="flight")
        if not flights.exists():
            missing.append("Flight details")
        for flight in flights:
            if not flight.start_at:
                missing.append("Flight departure time")
            if not flight.origin or not flight.destination:
                missing.append("Flight airports")
            if flight.verification != "confirmed":
                missing.append("Confirmation of flight details")
        if self.airport_buffer_minutes is None:
            missing.append("Airport arrival buffer")
        if self.ground_minutes is None:
            missing.append("Ground transportation duration")
        return list(dict.fromkeys(missing))


class TripSegment(models.Model):
    trip = models.ForeignKey(Trip, related_name="segments", on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=[("flight", "Flight"), ("stay", "Hotel stay")])
    label = models.CharField(max_length=200)
    origin = models.CharField(max_length=100, blank=True)
    destination = models.CharField(max_length=100, blank=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(
        max_length=80, default="America/Chicago", validators=[validate_zone]
    )
    arrival_timezone = models.CharField(
        max_length=80, default="America/Chicago", validators=[validate_zone]
    )
    verification = models.CharField(
        max_length=20,
        choices=[("user_reported", "User reported"), ("confirmed", "User confirmed")],
        default="user_reported",
    )
    revision = models.PositiveIntegerField(default=1)

    def clean(self):
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError("Arrival/end must follow departure/start.")

    def save(self, *args, **kwargs):
        if self.pk:
            self.revision += 1
        super().save(*args, **kwargs)


class ScheduledJob(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    principal = models.CharField(max_length=80)
    kind = models.CharField(max_length=20)
    key = models.CharField(max_length=240, unique=True)
    due_at = models.DateTimeField(db_index=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    lease_token = models.CharField(max_length=64, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)


class Delivery(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    principal = models.CharField(max_length=80)
    key = models.CharField(max_length=280, unique=True)
    content = models.TextField()
    refs = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    previewed_at = models.DateTimeField(null=True, blank=True)
    provider_ref = models.CharField(max_length=100, blank=True)


class WorkflowPolicy(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    workflow = models.CharField(max_length=40)
    vendor = models.CharField(max_length=200)
    enabled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "owner", "workflow", "vendor"], name="workflow_policy_unique"
            )
        ]


class ActionProposal(OwnedRecord):
    title = models.CharField(max_length=200)
    workflow = models.CharField(
        max_length=40,
        choices=[
            ("routine_appointment", "Routine appointment"),
            ("household_task", "Household task"),
            ("gift", "Gift"),
        ],
    )
    vendor = models.CharField(max_length=200)
    affected_person = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="affected_actions"
    )
    subtotal_cents = models.PositiveIntegerField(null=True, blank=True)
    fees_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    terms = models.TextField(max_length=2000, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    availability_confirmed = models.BooleanField(default=False)
    recurring = models.BooleanField(default=False)
    quote_expires_at = models.DateTimeField(null=True, blank=True)
    purchase_group = models.UUIDField(default=uuid.uuid4)
    status = models.CharField(max_length=30, default="draft")
    ready_by = models.CharField(max_length=20, blank=True)
    receipt = models.CharField(max_length=200, blank=True)

    @property
    def total_cents(self):
        return None if self.subtotal_cents is None else self.subtotal_cents + self.fees_cents

    def clean(self):
        super().clean()
        if (
            self.affected_person_id
            and not Membership.objects.filter(
                household_id=self.household_id, user_id=self.affected_person_id
            ).exists()
        ):
            raise ValidationError("The affected person must belong to the household.")


class Approval(models.Model):
    proposal = models.ForeignKey(ActionProposal, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    decision = models.CharField(max_length=10, default="approved")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["proposal", "revision"], name="approval_revision_unique"
            )
        ]


class BudgetConfig(models.Model):
    household = models.OneToOneField(Household, on_delete=models.CASCADE)
    monthly_limit_cents = models.PositiveIntegerField(default=30000)
    variable_limit_cents = models.PositiveIntegerField(default=5000)
    costs_confirmed = models.BooleanField(default=False)


class BudgetCommitment(models.Model):
    budget = models.ForeignKey(BudgetConfig, related_name="commitments", on_delete=models.CASCADE)
    label = models.CharField(max_length=120)
    monthly_cents = models.PositiveIntegerField(null=True, blank=True)

    @property
    def monthly_display(self):
        return None if self.monthly_cents is None else f"{self.monthly_cents / 100:.2f}"


class UsageReservation(models.Model):
    budget = models.ForeignKey(BudgetConfig, on_delete=models.CASCADE)
    billing_month = models.DateField()
    key = models.CharField(max_length=120, unique=True)
    estimate_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="reserved")
    actual_cents = models.PositiveIntegerField(null=True, blank=True)


class UsageEvent(models.Model):
    reservation = models.OneToOneField(UsageReservation, on_delete=models.CASCADE)
    amount_cents = models.PositiveIntegerField()
    estimated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    principal = models.CharField(max_length=80)
    object_id = models.PositiveIntegerField()
    event = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
