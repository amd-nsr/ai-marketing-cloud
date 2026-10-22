import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalises_email_and_hashes_password():
    user = User.objects.create_user("Owner@Example.COM", "a-long-test-password")
    assert user.email == "owner@example.com"
    assert user.password != "a-long-test-password"
    assert user.check_password("a-long-test-password")
    assert not user.is_staff and not user.is_superuser


def test_email_is_unique_case_insensitively_at_database_level():
    User.objects.create_user("owner@example.com", "a-long-test-password")
    # Bypass manager normalisation to prove the database constraint itself holds.
    with pytest.raises(IntegrityError):
        User.objects.create(email="OWNER@example.com")


def test_authenticate_is_case_insensitive_on_email():
    User.objects.create_user("owner@example.com", "a-long-test-password")
    user = authenticate(email="Owner@Example.com", password="a-long-test-password")
    assert user is not None


def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser("admin@example.com", "a-long-test-password")
    assert admin.is_staff and admin.is_superuser


def test_create_superuser_rejects_inconsistent_flags():
    with pytest.raises(ValueError, match="superuser"):
        User.objects.create_superuser("a@example.com", "a-long-test-password", is_staff=False)


def test_primary_key_is_uuid():
    user = User.objects.create_user("uuid@example.com", "a-long-test-password")
    assert len(str(user.pk)) == 36
