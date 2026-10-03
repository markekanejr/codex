import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from workforce.models import Invitation, Membership, User


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitation(household, email):
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        household=household,
        email=email.lower(),
        token_hash=token_hash(token),
        expires_at=timezone.now() + timedelta(hours=24),
    )
    return invitation, token


@transaction.atomic
def accept_invitation(token, password):
    invitation = Invitation.objects.select_for_update().filter(token_hash=token_hash(token)).first()
    if not invitation or invitation.accepted_at or invitation.expires_at <= timezone.now():
        raise ValidationError("This invitation has expired or has already been used.")
    if User.objects.filter(email__iexact=invitation.email).exists():
        raise ValidationError(
            "This email already has an account. Contact your household administrator."
        )
    user = User(username=invitation.email, email=invitation.email)
    validate_password(password, user)
    user.set_password(password)
    user.save()
    Membership.objects.create(user=user, household=invitation.household, role="partner")
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    return user
