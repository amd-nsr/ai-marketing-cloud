from django.apps import AppConfig


class AdsConfig(AppConfig):
    name = "apps.ads"
    label = "ads"

    def ready(self) -> None:
        from . import mock_fixtures, workflows  # noqa: F401  (registration side effects)
