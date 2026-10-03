from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from workforce.models import User


class FoundationTests(TestCase):
    def test_login_required_and_login_page_available(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)

    def test_authenticated_home(self):
        user = User.objects.create_user(
            "alex", email="alex@example.test", password="sample-long-pass"
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(DEBUG=False)
    def test_demo_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("load_demo")
