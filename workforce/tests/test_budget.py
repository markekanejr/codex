from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from workforce.models import BudgetCommitment, BudgetConfig, Household, UsageEvent
from workforce.services.budgets import BudgetUnavailable, reserve, settle, summary
from workforce.tests.helpers import HouseholdCase


class BudgetTests(HouseholdCase):
    def setUp(self):
        self.household.pause_ai = False
        self.household.save()
        self.budget = BudgetConfig.objects.create(
            household=self.household,
            monthly_limit_cents=30000,
            variable_limit_cents=5000,
            costs_confirmed=True,
        )

    def test_fixed_commitments_reduce_variable_allowance(self):
        BudgetCommitment.objects.create(
            budget=self.budget, label="Existing service", monthly_cents=28000
        )
        reserve(self.household, 1900, "first")
        with self.assertRaises(BudgetUnavailable):
            reserve(self.household, 200, "second")

    def test_unknown_subscription_costs_block_reservations(self):
        BudgetCommitment.objects.create(budget=self.budget, label="Unknown service")
        with self.assertRaises(BudgetUnavailable):
            reserve(self.household, 1, "unknown")
        self.assertFalse(summary(self.budget)["known"])

    def test_unconfirmed_cost_inventory_blocks_reservations(self):
        self.budget.costs_confirmed = False
        self.budget.save()
        with self.assertRaises(BudgetUnavailable):
            reserve(self.household, 1, "not-confirmed")

    def test_reservation_and_settlement_are_idempotent(self):
        first = reserve(self.household, 1000, "same")
        self.assertEqual(reserve(self.household, 1000, "same").pk, first.pk)
        settle(first, actual_cents=700)
        settle(first, actual_cents=700)
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(summary(self.budget)["spent"], 700)
        self.assertEqual(summary(self.budget)["remaining"], 4300)

    def test_unknown_actual_cost_uses_conservative_reservation(self):
        first = reserve(self.household, 1000, "estimate")
        settle(first)
        self.assertEqual(summary(self.budget)["spent"], 1000)
        self.assertTrue(UsageEvent.objects.get().estimated)

    def test_cancel_releases_reservation(self):
        first = reserve(self.household, 1000, "cancel")
        settle(first, cancel=True)
        self.assertEqual(summary(self.budget)["remaining"], 5000)

    def test_negative_costs_are_rejected(self):
        with self.assertRaises(BudgetUnavailable):
            reserve(self.household, -1, "negative")

    def test_partner_cannot_change_costs_or_threshold(self):
        self.client.force_login(self.jamie)
        response = self.client.post(
            "/settings/budget/",
            {
                "operation": "budget",
                "monthly_limit": "999",
                "variable_limit": "999",
                "auto_limit": "999",
                "costs_confirmed": "on",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.household.refresh_from_db()
        self.assertEqual(self.household.auto_limit_cents, 10000)

    def test_unknown_cost_is_explicit_in_ui(self):
        self.client.force_login(self.alex)
        self.client.post(
            "/settings/budget/",
            {"operation": "commitment", "label": "Unknown service", "monthly_cost": ""},
        )
        self.assertContains(self.client.get("/settings/budget/"), "Cost unknown")


class BudgetConcurrencyTests(TransactionTestCase):
    def test_concurrent_reservations_cannot_oversubscribe(self):
        household = Household.objects.create(name="Example", pause_ai=False)
        budget = BudgetConfig.objects.create(
            household=household,
            monthly_limit_cents=100,
            variable_limit_cents=100,
            costs_confirmed=True,
        )
        barrier = Barrier(2)

        def request(key):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                try:
                    return reserve(household, 80, key).pk
                except BudgetUnavailable:
                    return None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(request, ["one", "two"]))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(summary(budget)["reserved"], 80)
