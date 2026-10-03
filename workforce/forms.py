from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.utils.dateparse import parse_datetime

from workforce.models import (
    ActionProposal,
    Membership,
    PlanItem,
    Routine,
    SourceRecord,
    Trip,
    TripSegment,
    User,
)
from workforce.services.access import scoped


class WallTimeField(forms.DateTimeField):
    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        try:
            result = parse_datetime(value)
        except ValueError:
            result = None
        if result is None:
            raise forms.ValidationError("Enter a valid date and time.")
        return result.replace(tzinfo=None)


class OwnedForm(forms.ModelForm):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_zone = Membership.objects.get(user=user).household.timezone
        if "source" in self.fields:
            self.fields["source"].queryset = scoped(SourceRecord, user)
        for name, field in list(self.fields.items()):
            if isinstance(field, forms.DateTimeField):
                self.fields[name] = WallTimeField(required=field.required, label=field.label)
                self.fields[name].widget = forms.DateTimeInput(
                    attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
                )
                value = getattr(self.instance, name, None)
                if value is not None:
                    zone_name = (
                        getattr(self.instance, "arrival_timezone", None)
                        if name == "end_at"
                        else None
                    )
                    zone_name = zone_name or getattr(self.instance, "timezone", self.default_zone)
                    self.initial[name] = value.astimezone(ZoneInfo(zone_name)).replace(tzinfo=None)
            elif isinstance(field, forms.DateField):
                field.widget = forms.DateInput(attrs={"type": "date"})
            elif isinstance(field, forms.TimeField):
                field.widget = forms.TimeInput(attrs={"type": "time"})

    def clean(self):
        data = super().clean()
        zone_name = data.get("timezone", self.default_zone)
        if zone_name:
            try:
                zone = ZoneInfo(zone_name)
            except (ZoneInfoNotFoundError, ValueError):
                return data
            for name in [
                key for key, field in self.fields.items() if isinstance(field, WallTimeField)
            ]:
                if data.get(name):
                    actual_zone = zone
                    if name == "end_at" and data.get("arrival_timezone"):
                        try:
                            actual_zone = ZoneInfo(data["arrival_timezone"])
                        except (ZoneInfoNotFoundError, ValueError):
                            continue
                    entered = data[name].replace(tzinfo=None)
                    candidate = entered.replace(tzinfo=actual_zone, fold=0)
                    from datetime import UTC

                    if (
                        candidate.astimezone(UTC).astimezone(actual_zone).replace(tzinfo=None)
                        != entered
                    ):
                        self.add_error(
                            name, "This local time does not exist in the selected timezone."
                        )
                    else:
                        data[name] = candidate
        return data


class PlanForm(OwnedForm):
    class Meta:
        model = PlanItem
        fields = [
            "title",
            "kind",
            "audience",
            "status",
            "start_at",
            "end_at",
            "due_at",
            "timezone",
            "source",
        ]


class RoutineForm(OwnedForm):
    weekdays = forms.MultipleChoiceField(
        choices=list(
            enumerate(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            )
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    def clean_weekdays(self):
        return [int(day) for day in self.cleaned_data["weekdays"]]

    class Meta:
        model = Routine
        fields = [
            "title",
            "audience",
            "local_time",
            "timezone",
            "rule",
            "weekdays",
            "active_from",
            "active_until",
            "active",
        ]


class TripForm(OwnedForm):
    class Meta:
        model = Trip
        fields = [
            "title",
            "audience",
            "departure_date",
            "status",
            "airport_buffer_minutes",
            "ground_minutes",
        ]


class SegmentForm(OwnedForm):
    class Meta:
        model = TripSegment
        fields = [
            "kind",
            "label",
            "origin",
            "destination",
            "start_at",
            "end_at",
            "timezone",
            "arrival_timezone",
            "verification",
        ]


class SourceForm(OwnedForm):
    class Meta:
        model = SourceRecord
        fields = ["title", "audience", "provenance", "data"]


class InvitationAcceptForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("confirm_password"):
            raise forms.ValidationError("Passwords must match.")
        return data


class ActionForm(OwnedForm):
    subtotal = forms.DecimalField(
        max_digits=9,
        decimal_places=2,
        min_value=0,
        required=False,
        label="Quoted price (USD)",
        help_text="Leave blank if the full price is still unknown.",
    )
    fees = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, initial=0, label="Taxes and fees (USD)"
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["affected_person"].queryset = User.objects.filter(
            membership__household=Membership.objects.get(user=user).household
        )
        self.fields["affected_person"].initial = user.pk
        if self.instance.pk:
            self.fields["subtotal"].initial = (
                None if self.instance.subtotal_cents is None else self.instance.subtotal_cents / 100
            )
            self.fields["fees"].initial = self.instance.fees_cents / 100

    def clean(self):
        data = super().clean()
        self.instance.subtotal_cents = (
            None if data.get("subtotal") is None else int(data["subtotal"] * 100)
        )
        self.instance.fees_cents = (
            int(data.get("fees", 0) * 100) if data.get("fees") is not None else 0
        )
        return data

    class Meta:
        model = ActionProposal
        fields = [
            "title",
            "audience",
            "workflow",
            "vendor",
            "affected_person",
            "currency",
            "terms",
            "requested_at",
            "availability_confirmed",
            "recurring",
            "quote_expires_at",
            "subtotal",
            "fees",
        ]


class BudgetForm(forms.Form):
    monthly_limit = forms.DecimalField(
        min_value=0, decimal_places=2, max_digits=9, label="Total monthly tools budget (USD)"
    )
    variable_limit = forms.DecimalField(
        min_value=0, decimal_places=2, max_digits=9, label="Monthly usage allowance (USD)"
    )
    auto_limit = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        max_digits=9,
        label="Routine purchase approval threshold (USD)",
    )
    costs_confirmed = forms.BooleanField(
        required=False,
        label="All existing paid subscriptions and service commitments are listed below.",
    )


class CommitmentForm(forms.Form):
    label = forms.CharField(max_length=120, label="Subscription or service")
    monthly_cost = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        max_digits=9,
        required=False,
        label="Monthly charge (USD)",
        help_text="Leave blank if you don't know yet. Unknown charges block paid usage.",
    )


class PolicyForm(forms.Form):
    workflow = forms.ChoiceField(choices=ActionProposal._meta.get_field("workflow").choices)
    vendor = forms.CharField(max_length=200)
    enabled = forms.BooleanField(
        required=False, label="Allow routine proposals for my own commitments with this vendor."
    )
