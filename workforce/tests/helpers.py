from django.test import TestCase

from workforce.models import Household, Membership, User


class HouseholdCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.household = Household.objects.create(name="Fictional household")
        cls.alex = User.objects.create_user(
            "alex@example.test", email="alex@example.test", password="fictional-test-password"
        )
        cls.jamie = User.objects.create_user(
            "jamie@example.test", email="jamie@example.test", password="fictional-test-password"
        )
        cls.outsider = User.objects.create_user(
            "outside@example.test", email="outside@example.test"
        )
        Membership.objects.create(
            household=cls.household, user=cls.alex, role="owner", pricing_approver=True
        )
        Membership.objects.create(household=cls.household, user=cls.jamie, role="partner")
        cls.other_household = Household.objects.create(name="Different household")
        Membership.objects.create(household=cls.other_household, user=cls.outsider, role="owner")
