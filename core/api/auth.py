import os

from django.contrib.auth.models import User
from django.http import HttpRequest


def no_auth_enabled() -> bool:
    return os.environ.get("NO_AUTH", "").lower() in ("1", "true", "yes")


def get_or_create_admin() -> User:
    user, created = User.objects.get_or_create(
        username="admin",
        defaults={"is_staff": True, "is_superuser": True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


def session_auth(request: HttpRequest):
    if no_auth_enabled():
        user = get_or_create_admin()
        request.user = user
        return user
    if request.user.is_authenticated:
        return request.user
    return None
