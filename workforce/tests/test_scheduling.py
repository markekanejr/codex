from datetime import UTC, date, datetime, time, timedelta

from django.test import SimpleTestCase

from workforce.models import PlanItem, Routine, ScheduledJob, Trip, TripSegment
from workforce.services.briefings import travel_preparation
from workforce.services.scheduling import local_instant, schedule_day
from workforce.tests.helpers import HouseholdCase


class TimeTests(SimpleTestCase):
    def test_spring_and_autumn_keep_local_time(self):
        spring_before = local_instant(date(2026, 3, 7), time(7, 30), "America/Chicago")
        spring_after = local_instant(date(2026, 3, 8), time(7, 30), "America/Chicago")
        self.assertEqual(spring_after - spring_before, timedelta(hours=23))
        fall_before = local_instant(date(2026, 10, 31), time(7, 30), "America/Chicago")
        fall_after = local_instant(date(2026, 11, 1), time(7, 30), "America/Chicago")
        self.assertEqual(fall_after - fall_before, timedelta(hours=25))

    def test_nonexistent_time_moves_to_next_valid_minute(self):
        instant = local_instant(date(2026, 3, 8), time(2, 30), "America/Chicago")
        self.assertEqual(instant, datetime(2026, 3, 8, 8, 0, tzinfo=UTC))

    def test_fold_uses_first_occurrence_once(self):
        instant = local_instant(date(2026, 11, 1), time(1, 30), "America/Chicago")
        self.assertEqual(instant, datetime(2026, 11, 1, 6, 30, tzinfo=UTC))


class SchedulingTests(HouseholdCase):
    def test_each_private_principal_and_shared_occurrence_coexist(self):
        day = date(2026, 5, 4)
        schedule_day(self.household, day)
        schedule_day(self.household, day)
        jobs = ScheduledJob.objects.filter(kind="briefing")
        self.assertEqual(jobs.count(), 3)
        self.assertEqual(
            set(jobs.values_list("principal", flat=True)),
            {"shared", f"user:{self.alex.pk}", f"user:{self.jamie.pk}"},
        )

    def test_early_event_preparation_is_previous_evening(self):
        day = date(2026, 5, 8)
        plan = PlanItem.objects.create(
            household=self.household,
            owner=self.alex,
            title="Early activity",
            audience="shared",
            status="confirmed",
            start_at=local_instant(day, time(7), "America/Chicago"),
        )
        schedule_day(self.household, day)
        job = ScheduledJob.objects.get(kind="reminder")
        self.assertEqual(
            job.due_at, local_instant(day - timedelta(days=1), time(19), "America/Chicago")
        )
        plan.status = "canceled"
        plan.save()
        from workforce.services.jobs import run_once

        run_once(job.due_at)
        job.refresh_from_db()
        self.assertEqual(job.status, "canceled")

    def test_early_weekly_routine_generates_prior_evening_job(self):
        Routine.objects.create(
            household=self.household,
            owner=self.alex,
            title="Practice",
            audience="shared",
            rule="weekly",
            weekdays=[4],
            local_time=time(7),
            active_from=date(2026, 1, 1),
        )
        schedule_day(self.household, date(2026, 5, 8))
        self.assertEqual(ScheduledJob.objects.filter(kind="reminder").count(), 1)

    def test_unknown_flight_time_does_not_generate_departure(self):
        trip = Trip.objects.create(
            household=self.household,
            owner=self.alex,
            title="Example",
            airport_buffer_minutes=120,
            ground_minutes=30,
        )
        segment = TripSegment.objects.create(
            trip=trip,
            kind="flight",
            label="Flight",
            origin="AAA",
            destination="BBB",
            verification="confirmed",
        )
        self.assertEqual(travel_preparation(trip), [])
        segment.start_at = local_instant(date(2026, 5, 8), time(14), "America/Chicago")
        segment.save()
        steps = travel_preparation(trip)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[1][1], segment.start_at - timedelta(minutes=150))
