import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from workforce.models import Household, Membership, User


class Command(BaseCommand):
    help = "Create an initial household account with a privately entered password."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="Our household")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("This account already exists; no changes made.")
        password = getpass.getpass("New password (hidden): ")
        if password != getpass.getpass("Confirm password (hidden): "):
            raise CommandError("Passwords did not match.")
        user = User(username=email, email=email)
        validate_password(password, user)
        user.set_password(password)
        user.save()
        household = Household.objects.create(name=options["name"])
        Membership.objects.create(
            user=user, household=household, role="owner", pricing_approver=True
        )
        self.stdout.write("Household and initial account created.")
