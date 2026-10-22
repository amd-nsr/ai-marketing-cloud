"""Cross-tenant access must be impossible, whatever IDs the client supplies."""

import uuid

import pytest

from apps.organizations.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_tenants(org_client):
    client_a, org_a = org_client("owner")
    client_b, org_b = org_client("owner")
    return client_a, org_a, client_b, org_b


@pytest.mark.parametrize(
    "path",
    ["", "me/", "members/", "invitations/", "audit-events/"],
)
def test_non_member_gets_404_for_other_org(two_tenants, path):
    client_a, _, _, org_b = two_tenants
    response = client_a.get(f"/api/v1/orgs/{org_b.id}/{path}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unknown_org_is_indistinguishable_from_foreign_org(two_tenants):
    client_a, *_ = two_tenants
    assert client_a.get(f"/api/v1/orgs/{uuid.uuid4()}/").status_code == 404


def test_cannot_modify_member_of_other_org_via_own_org_url(two_tenants):
    client_a, org_a, _, org_b = two_tenants
    victim = Membership.objects.get(organization=org_b)
    # Object from org B addressed through org A's URL.
    response = client_a.patch(
        f"/api/v1/orgs/{org_a.id}/members/{victim.id}/", {"role": "viewer"}, format="json"
    )
    assert response.status_code == 404
    delete = client_a.delete(f"/api/v1/orgs/{org_a.id}/members/{victim.id}/")
    assert delete.status_code == 404
    victim.refresh_from_db()
    assert victim.role == "owner"


def test_cannot_write_to_other_org(two_tenants):
    client_a, _, _, org_b = two_tenants
    response = client_a.post(
        f"/api/v1/orgs/{org_b.id}/invitations/",
        {"email": "spy@example.com", "role": "viewer"},
        format="json",
    )
    assert response.status_code == 404


def test_anonymous_gets_403_not_data(api_client, two_tenants):
    _, org_a, *_ = two_tenants
    assert api_client.get(f"/api/v1/orgs/{org_a.id}/").status_code == 403


def test_scoped_viewset_must_precede_drf_mixins():
    from rest_framework import mixins

    from apps.organizations.api import OrganizationScopedViewSet

    with pytest.raises(TypeError, match="before DRF mixins"):

        class _Wrong(mixins.CreateModelMixin, OrganizationScopedViewSet):
            pass


def _org_routes():
    """Every route under /api/v1/orgs/<org_id>/, with path converters filled in."""
    import re

    from django.urls import URLPattern, URLResolver, get_resolver

    routes: set[str] = set()

    def walk(patterns, prefix):
        for p in patterns:
            route = prefix + str(p.pattern)
            if isinstance(p, URLResolver):
                walk(p.url_patterns, route)
            elif isinstance(p, URLPattern) and "<uuid:org_id>" in route:
                routes.add(route)

    walk(get_resolver().url_patterns, "")
    filled = set()
    for route in routes:
        if "\\." in route:  # DRF format-suffix variants (.json) duplicate real routes
            continue
        route = route.replace("^", "").replace("$", "")
        route = re.sub(r"\(\?P<org_id>[^)]*\)", "<uuid:org_id>", route)
        route = re.sub(r"\(\?P<\w+>\\d\+\)", "1", route)
        route = re.sub(r"\(\?P<\w+>[^)]*\)", lambda _: str(uuid.uuid4()), route)
        route = re.sub(r"<(?!uuid:org_id>)[^>]+>", lambda _: str(uuid.uuid4()), route)
        filled.add(route)
    return sorted(filled)


ORG_ROUTES = _org_routes()


def test_route_discovery_finds_the_api():
    assert len(ORG_ROUTES) > 40
    assert any("operations/" in r for r in ORG_ROUTES)


@pytest.mark.parametrize("route", ORG_ROUTES)
def test_every_org_route_is_404_for_non_members(two_tenants, route):
    client_a, _, _, org_b = two_tenants
    from django.urls import resolve

    path = "/" + route.replace("<uuid:org_id>", str(org_b.id))
    resolve(path)  # the generated path must hit a real view, not a URL miss
    for method in ("get", "post", "patch", "delete"):
        response = getattr(client_a, method)(path, {}, format="json")
        assert response.status_code in (404, 405), (method, path, response.status_code)
        if response.status_code == 405:
            continue
        assert response.json()["error"]["code"] == "not_found"
