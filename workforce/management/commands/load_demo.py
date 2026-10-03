from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from workforce.models import Household, Membership, PlanItem, Trip, User


class Command(BaseCommand):
    help = "Create fictional demo identities without usable passwords (development only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo loading is disabled outside development.")
        household, _ = Household.objects.get_or_create(name="Example household")
        for name in ("alex", "jamie"):
            user, created = User.objects.get_or_create(
                username=f"{name}@example.test",
                defaults={"email": f"{name}@example.test", "first_name": name.title()},
            )
            if created:
                user.set_unusable_password()
                user.save()
            Membership.objects.get_or_create(
                user=user,
                defaults={
                    "household": household,
                    "role": "owner" if name == "alex" else "partner",
                    "pricing_approver": name == "alex",
                },
            )
        owner = User.objects.get(username="alex@example.test")
        PlanItem.objects.get_or_create(
            household=household,
            owner=owner,
            title="Plan a weekend walk",
            defaults={"audience": "shared"},
        )
        Trip.objects.get_or_create(
            household=household,
            owner=owner,
            title="Example getaway",
            defaults={"audience": "shared"},
        )
        self.stdout.write("Fictional demo identities ready; no login passwords created.")
