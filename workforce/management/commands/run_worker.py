import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from workforce.models import Household
from workforce.services.jobs import run_once
from workforce.services.scheduling import schedule_day


class Command(BaseCommand):
    help = "Generate local schedules and process durable jobs in preview mode."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll", type=float, default=5)

    def handle(self, *args, **options):
        while True:
            now = timezone.now()
            for household in Household.objects.all():
                day = now.astimezone(ZoneInfo(household.timezone)).date()
                schedule_day(household, day)
                schedule_day(household, day + timedelta(days=1))
            count = run_once(now)
            if options["once"]:
                self.stdout.write(f"Processed {count} preview jobs.")
                return
            time.sleep(max(1, options["poll"]))
