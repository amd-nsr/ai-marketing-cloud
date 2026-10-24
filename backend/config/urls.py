from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.brand.views import ReferenceDataView
from apps.operations.views import BackgroundHealthView
from apps.social.views import OAuthCallbackView

api_v1: list[URLPattern | URLResolver] = [
    path("health/background/", BackgroundHealthView.as_view(), name="health-background"),
    path("health/", include("apps.core.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("orgs/", include("apps.organizations.urls")),
    path("reference-data/", ReferenceDataView.as_view(), name="reference-data"),
    path("social/oauth/callback/", OAuthCallbackView.as_view(), name="social-oauth-callback"),
    path("meta/", include("apps.meta.public_urls")),
    path("schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
]

handler404 = "apps.core.exceptions.json_not_found"
handler500 = "apps.core.exceptions.json_server_error"

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include(api_v1)),
    path(settings.ADMIN_URL, admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [
        path(
            "api/v1/docs/",
            SpectacularSwaggerView.as_view(url_name="openapi-schema"),
            name="api-docs",
        ),
    ]
