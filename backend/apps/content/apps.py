from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "apps.content"
    label = "content"

    def ready(self) -> None:
        from apps.usage.storage import register_storage_model

        from . import mock_fixtures, workflows  # noqa: F401  (registration side effects)
        from .models import ContentAsset

        register_storage_model(ContentAsset)
