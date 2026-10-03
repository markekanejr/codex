from django.test import SimpleTestCase, override_settings


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
