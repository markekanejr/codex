import secrets

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from config.secrets import production_secret


class ProductionSecretTests(SimpleTestCase):
    def test_provider_sized_key_has_stable_django_compatible_expansion(self):
        value = secrets.token_hex(16)
        result = production_secret(value)
        self.assertEqual(len(result), 64)
        self.assertGreaterEqual(len(set(result)), 5)
        self.assertEqual(result, production_secret(value))
        self.assertNotEqual(result, production_secret(secrets.token_hex(16)))

    def test_existing_long_key_is_preserved(self):
        value = secrets.token_urlsafe(64)
        self.assertEqual(production_secret(value), value)

    def test_short_repeated_and_development_keys_are_rejected(self):
        for value in ("too-short", "a" * 64, "django-insecure-" + secrets.token_hex(32)):
            with self.subTest(case=len(value)), self.assertRaises(ImproperlyConfigured):
                production_secret(value)


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=["preview.example.test"],
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
)
class HostedSecurityTests(SimpleTestCase):
    def test_plain_http_redirects_to_https(self):
        response = self.client.get("/accounts/login/", HTTP_HOST="preview.example.test")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://preview.example.test/accounts/login/")

    def test_proxy_https_login_sets_secure_csrf_cookie(self):
        response = self.client.get(
            "/accounts/login/",
            HTTP_HOST="preview.example.test",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["csrftoken"]["secure"])
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_unlisted_hostname_is_rejected(self):
        response = self.client.get(
            "/accounts/login/", HTTP_HOST="unknown.example.test", secure=True
        )
        self.assertEqual(response.status_code, 400)
