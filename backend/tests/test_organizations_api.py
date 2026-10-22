import pytest
from django.core import mail

from apps.audit.models import AuditEvent
from apps.organizations.models import Invitation, Membership
from apps.organizations.roles import ROLE_PERMISSIONS, Perm, Role

pytestmark = pytest.mark.django_db


def test_create_org_makes_caller_owner(make_user, api_client):
    user = make_user()
    api_client.force_authenticate(user)
    response = api_client.post("/api/v1/orgs/", {"name": "Acme Coffee"}, format="json")
    assert response.status_code == 201
    org_id = response.json()["id"]
    assert Membership.objects.get(organization_id=org_id, user=user).role == Role.OWNER
    me = api_client.get("/api/v1/auth/me/").json()
    assert me["memberships"][0]["organization"]["id"] == org_id
    assert Perm.CONTENT_APPROVE in me["memberships"][0]["permissions"]


def test_list_only_shows_callers_orgs(org_client, make_org):
    client, org = org_client("editor")
    make_org("Someone Else")
    names = [o["name"] for o in client.get("/api/v1/orgs/").json()["results"]]
    assert names == [org.name]


def test_role_permission_matrix_is_as_documented():
    assert ROLE_PERMISSIONS[Role.OWNER] == ROLE_PERMISSIONS[Role.ADMIN]
    analyst = ROLE_PERMISSIONS[Role.ANALYST]
    assert Perm.ANALYTICS_VIEW in analyst
    assert not analyst & {Perm.PUBLISHING_PUBLISH, Perm.SOCIAL_MANAGE, Perm.CONTENT_EDIT}
    editor = ROLE_PERMISSIONS[Role.EDITOR]
    assert {Perm.CONTENT_EDIT, Perm.CONTENT_SUBMIT} <= editor
    assert not editor & {Perm.CONTENT_APPROVE, Perm.PUBLISHING_PUBLISH, Perm.MEMBERS_MANAGE}
    viewer = ROLE_PERMISSIONS[Role.VIEWER]
    assert all(p.endswith(".view") for p in viewer)


@pytest.mark.parametrize(
    ("role", "status"), [("owner", 200), ("admin", 200), ("editor", 403), ("viewer", 403)]
)
def test_only_managers_can_rename_org(org_client, role, status):
    client, org = org_client(role)
    response = client.patch(f"/api/v1/orgs/{org.id}/", {"name": "Renamed"}, format="json")
    assert response.status_code == status


def test_invitation_flow(org_client, make_user, api_client, django_capture_on_commit_callbacks):
    client, org = org_client("admin")
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/v1/orgs/{org.id}/invitations/",
            {"email": "New.Hire@example.com", "role": "editor"},
            format="json",
        )
    assert response.status_code == 201, response.json()
    assert len(mail.outbox) == 1
    invitation = Invitation.objects.get()
    assert invitation.token in mail.outbox[0].body

    # Duplicate pending invitation is a conflict.
    dup = client.post(
        f"/api/v1/orgs/{org.id}/invitations/",
        {"email": "new.hire@example.com", "role": "viewer"},
        format="json",
    )
    assert dup.status_code == 409

    # A different user cannot accept it.
    stranger = make_user("stranger@example.com")
    api_client.force_authenticate(stranger)
    wrong = api_client.post(
        "/api/v1/orgs/invitations/accept/", {"token": invitation.token}, format="json"
    )
    assert wrong.status_code == 403

    invitee = make_user("new.hire@example.com")
    api_client.force_authenticate(invitee)
    ok = api_client.post(
        "/api/v1/orgs/invitations/accept/", {"token": invitation.token}, format="json"
    )
    assert ok.status_code == 200
    assert Membership.objects.get(organization=org, user=invitee).role == "editor"
    again = api_client.post(
        "/api/v1/orgs/invitations/accept/", {"token": invitation.token}, format="json"
    )
    assert again.status_code == 400


def test_admin_cannot_invite_or_promote_owner(org_client, make_user, add_member):
    client, org = org_client("admin")
    invite = client.post(
        f"/api/v1/orgs/{org.id}/invitations/",
        {"email": "boss@example.com", "role": "owner"},
        format="json",
    )
    assert invite.status_code == 403
    member = add_member(org, make_user(), "editor")
    promote = client.patch(
        f"/api/v1/orgs/{org.id}/members/{member.id}/", {"role": "owner"}, format="json"
    )
    assert promote.status_code == 403


def test_last_owner_cannot_be_demoted_or_leave(org_client):
    client, org = org_client("owner")
    me = Membership.objects.get(organization=org, user=client.user)
    demote = client.patch(
        f"/api/v1/orgs/{org.id}/members/{me.id}/", {"role": "admin"}, format="json"
    )
    assert demote.status_code == 409
    leave = client.delete(f"/api/v1/orgs/{org.id}/members/{me.id}/")
    assert leave.status_code == 409


def test_any_member_can_leave(org_client):
    client, org = org_client("viewer")
    me = Membership.objects.get(organization=org, user=client.user)
    assert client.delete(f"/api/v1/orgs/{org.id}/members/{me.id}/").status_code == 204
    assert client.get(f"/api/v1/orgs/{org.id}/").status_code == 404


def test_audit_log_visible_to_admins_only(org_client):
    client, org = org_client("owner")
    client.patch(f"/api/v1/orgs/{org.id}/", {"name": "Renamed"}, format="json")
    events = client.get(f"/api/v1/orgs/{org.id}/audit-events/").json()["results"]
    assert {e["action"] for e in events} >= {"organization.created", "organization.updated"}
    viewer, _ = org_client("viewer", org=org)
    assert viewer.get(f"/api/v1/orgs/{org.id}/audit-events/").status_code == 403
    assert AuditEvent.objects.filter(organization=org).count() >= 2
