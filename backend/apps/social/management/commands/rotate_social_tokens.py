"""Re-encrypt every stored platform token with the first SOCIAL_TOKEN_ENCRYPTION_KEYS key.

Run after prepending a new key; afterwards the old key can be removed.
"""

from typing import Any

from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.social import crypto
from apps.social.models import SocialAccount


class Command(BaseCommand):
    help = "Re-encrypt stored social tokens with the current primary key."

    def handle(self, *args: Any, **options: Any) -> None:
        rotated = unreadable = 0
        for pk in SocialAccount.objects.values_list("pk", flat=True).iterator():
            with transaction.atomic():
                account = SocialAccount.objects.select_for_update().get(pk=pk)
                try:
                    account.access_token_enc = crypto.rotate(account.access_token_enc)
                    account.refresh_token_enc = crypto.rotate(account.refresh_token_enc)
                except InvalidToken:
                    unreadable += 1
                    self.stderr.write(f"Account {pk}: no configured key decrypts its tokens.")
                    continue
                account.save(update_fields=["access_token_enc", "refresh_token_enc", "updated_at"])
                rotated += 1
        self.stdout.write(f"Rotated {rotated} account(s); {unreadable} unreadable.")
