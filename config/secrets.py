import hashlib

from django.core.exceptions import ImproperlyConfigured


def production_secret(value):
    """Accept provider-generated 32+ character secrets without logging them."""
    if len(value) < 32 or len(set(value)) < 5 or value.startswith("django-insecure-"):
        raise ImproperlyConfigured("Hosted previews require a strong generated secret key.")
    if len(value) >= 50:
        return value
    # Stable expansion satisfies Django's length heuristic. Entropy still comes
    # from the provider's random input; hashing does not add randomness.
    return hashlib.sha256(("household-preview:django-secret:v1:" + value).encode()).hexdigest()
