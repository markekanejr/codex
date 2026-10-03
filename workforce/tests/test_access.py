from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from workforce.models import Invitation, PlanItem, SourceRecord, Trip, TripSegment
from workforce.services.invitations import accept_invitation, issue_invitation
from workforce.tests.helpers import HouseholdCase


class AccessTests(HouseholdCase):
    def setUp(self):
        self.shared = PlanItem.objects.create(
            household=self.household, owner=self.alex, audience="shared", title="Shared outing"
        )
        self.private = PlanItem.objects.create(
            household=self.household, owner=self.jamie, audience="private", title="Secret surprise"
        )
        self.private_trip = Trip.objects.create(
            household=self.household, owner=self.jamie, title="Private trip"
        )
        self.client.force_login(self.alex)

    def test_list_and_export_hide_partner_private_items(self):
        response = self.client.get("/plans/")
        self.assertContains(response, "Shared outing")
        self.assertNotContains(response, "Secret surprise")
        data = self.client.get("/plans/export/").json()["plans"]
        self.assertEqual([row["id"] for row in data], [self.shared.pk])

    def test_detail_and_edit_reject_guessed_private_ids(self):
        self.assertEqual(self.client.get(f"/plans/{self.private.pk}/edit/").status_code, 404)
        self.assertEqual(self.client.get(f"/trips/{self.private_trip.pk}/").status_code, 404)
        self.assertEqual(
            self.client.post(f"/plans/{self.private.pk}/edit/", {"title": "Changed"}).status_code,
            404,
        )

    def test_shared_visibility_does_not_allow_changing_others_plans(self):
        self.client.force_login(self.jamie)
        self.assertContains(self.client.get("/plans/"), "Shared outing")
        self.assertEqual(self.client.get(f"/plans/{self.shared.pk}/edit/").status_code, 404)

    def test_other_household_cannot_read_or_write(self):
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get("/plans/"), "Shared outing")
        self.assertEqual(self.client.get(f"/plans/{self.shared.pk}/edit/").status_code, 404)
        self.assertEqual(self.client.get("/plans/export/").json()["plans"], [])

    def test_private_source_cannot_be_shared_through_link(self):
        source = SourceRecord.objects.create(
            household=self.household, owner=self.alex, title="Private source"
        )
        self.shared.source = source
        with self.assertRaises(ValidationError):
            self.shared.full_clean()
        response = self.client.post(
            f"/plans/{self.shared.pk}/edit/",
            {
                "title": "Derived content",
                "audience": "shared",
                "kind": "event",
                "status": "proposed",
                "timezone": "America/Chicago",
                "source": source.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "private source cannot")

    def test_changed_source_visibility_removes_shared_derivative(self):
        source = SourceRecord.objects.create(
            household=self.household, owner=self.alex, audience="shared", title="Source"
        )
        self.shared.source = source
        self.shared.save()
        source.audience = "private"
        source.save()
        self.client.force_login(self.jamie)
        self.assertNotContains(self.client.get("/plans/"), "Shared outing")
        self.assertEqual(
            [item["id"] for item in self.client.get("/plans/export/").json()["plans"]],
            [self.private.pk],
        )

    def test_wrong_household_source_rejected(self):
        source = SourceRecord.objects.create(
            household=self.other_household, owner=self.outsider, audience="shared", title="Other"
        )
        self.shared.source = source
        with self.assertRaises(ValidationError):
            self.shared.full_clean()

    def test_unknown_trip_fields_survive_form_save(self):
        response = self.client.post(
            "/trips/new/", {"title": "Fictional getaway", "audience": "shared", "status": "booked"}
        )
        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.get(title="Fictional getaway")
        self.assertIsNone(trip.departure_date)
        response = self.client.post(
            f"/trips/{trip.pk}/segments/new/",
            {
                "kind": "flight",
                "label": "Booked flight",
                "timezone": "America/Chicago",
                "arrival_timezone": "America/Chicago",
                "verification": "user_reported",
            },
        )
        self.assertEqual(response.status_code, 302)
        segment = TripSegment.objects.get(trip=trip)
        self.assertIsNone(segment.start_at)
        self.assertIn("Flight departure time", trip.missing_details)

    def test_invalid_timezone_is_form_error(self):
        response = self.client.post(
            "/plans/new/",
            {
                "title": "Bad timezone",
                "audience": "private",
                "kind": "event",
                "status": "proposed",
                "timezone": "not/a/timezone",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PlanItem.objects.filter(title="Bad timezone").exists())

    def test_invitation_single_use_and_expiry(self):
        invitation, token = issue_invitation(self.household, "new@example.test")
        user = accept_invitation(token, "MuchBetter-test-secret-384")
        self.assertEqual(user.membership.household, self.household)
        with self.assertRaises(ValidationError):
            accept_invitation(token, "MuchBetter-test-secret-384")
        expired, token2 = issue_invitation(self.household, "next@example.test")
        Invitation.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(ValidationError):
            accept_invitation(token2, "MuchBetter-test-secret-384")

    def test_partner_cannot_issue_invitation(self):
        self.client.force_login(self.jamie)
        self.client.post("/settings/", {"operation": "invite", "email": "invited@example.test"})
        self.assertEqual(Invitation.objects.count(), 0)

    def test_no_public_registration(self):
        self.assertEqual(self.client.get("/accounts/register/").status_code, 404)

    def test_segment_departure_and_arrival_use_distinct_timezones(self):
        trip = Trip.objects.create(
            household=self.household, owner=self.alex, title="Cross-zone trip"
        )
        response = self.client.post(
            f"/trips/{trip.pk}/segments/new/",
            {
                "kind": "flight",
                "label": "Cross-zone flight",
                "origin": "AAA",
                "destination": "BBB",
                "start_at": "2026-05-04T10:00",
                "end_at": "2026-05-04T11:00",
                "timezone": "America/Los_Angeles",
                "arrival_timezone": "America/New_York",
                "verification": "confirmed",
            },
        )
        # 10 Pacific is later than 11 Eastern: reject the apparently later wall time.
        self.assertEqual(response.status_code, 200)
        self.assertFalse(trip.segments.exists())

    def test_selected_timezone_not_server_timezone_controls_dst_validation(self):
        response = self.client.post(
            "/plans/new/",
            {
                "title": "UTC plan",
                "audience": "private",
                "kind": "event",
                "status": "confirmed",
                "timezone": "UTC",
                "start_at": "2026-03-08T02:30",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PlanItem.objects.get(title="UTC plan").start_at.hour, 2)
