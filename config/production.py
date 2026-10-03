from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import ALLOWED_HOSTS, DEBUG, SECRET_KEY

# The provider-owned preview domain is not ours to preload or cover recursively.
# HTTPS redirects, secure cookies and this hostname's HSTS remain enforced.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if DEBUG:
    raise ImproperlyConfigured("Hosted previews require DJANGO_DEBUG=false.")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured("Hosted previews require a strong generated secret key.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Hosted previews require explicit allowed hostnames.")
