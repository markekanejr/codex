from django.core.exceptions import ImproperlyConfigured

from .secrets import production_secret
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
SECRET_KEY = production_secret(SECRET_KEY)
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Hosted previews require explicit allowed hostnames.")
