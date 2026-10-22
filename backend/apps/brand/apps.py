from django.apps import AppConfig


class BrandConfig(AppConfig):
    name = "apps.brand"
    label = "brand"

    def ready(self) -> None:
        from apps.usage.storage import register_storage_model

        from .models import BrandAsset

        register_storage_model(BrandAsset)
