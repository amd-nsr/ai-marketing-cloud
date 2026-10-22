from django.apps import AppConfig


class MarketingConfig(AppConfig):
    name = "apps.marketing"
    label = "marketing"

    def ready(self) -> None:
        from . import mock_fixtures, workflows  # noqa: F401  (registration side effects)
