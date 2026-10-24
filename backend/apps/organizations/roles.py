"""Roles and the permissions each grants. The single source of truth for authorization.

Documented in docs/security/roles.md; tests assert the matrix in that document.
"""

from django.db import models


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    EDITOR = "editor", "Editor"
    ANALYST = "analyst", "Analyst"
    VIEWER = "viewer", "Viewer"


class Perm:
    ORG_VIEW = "org.view"
    ORG_MANAGE = "org.manage"
    MEMBERS_VIEW = "members.view"
    MEMBERS_MANAGE = "members.manage"
    BRAND_VIEW = "brand.view"
    BRAND_EDIT = "brand.edit"
    STRATEGY_VIEW = "strategy.view"
    STRATEGY_EDIT = "strategy.edit"
    CAMPAIGN_VIEW = "campaign.view"
    CAMPAIGN_EDIT = "campaign.edit"
    CONTENT_VIEW = "content.view"
    CONTENT_EDIT = "content.edit"
    CONTENT_SUBMIT = "content.submit"
    CONTENT_APPROVE = "content.approve"
    SOCIAL_VIEW = "social.view"
    SOCIAL_MANAGE = "social.manage"
    PUBLISHING_VIEW = "publishing.view"
    PUBLISHING_PUBLISH = "publishing.publish"
    ANALYTICS_VIEW = "analytics.view"
    RECOMMENDATIONS_VIEW = "recommendations.view"
    RECOMMENDATIONS_MANAGE = "recommendations.manage"
    AUTOMATION_VIEW = "automation.view"
    AUTOMATION_MANAGE = "automation.manage"
    AUTOMATION_APPROVE = "automation.approve"
    USAGE_VIEW = "usage.view"
    ADS_VIEW = "ads.view"
    ADS_DRAFT = "ads.draft"
    ADS_MANAGE = "ads.manage"
    AUDIT_VIEW = "audit.view"


ALL_PERMISSIONS: frozenset[str] = frozenset(
    v for k, v in vars(Perm).items() if not k.startswith("_") and isinstance(v, str)
)

_VIEWER = frozenset(
    {
        Perm.ORG_VIEW,
        Perm.BRAND_VIEW,
        Perm.STRATEGY_VIEW,
        Perm.CAMPAIGN_VIEW,
        Perm.CONTENT_VIEW,
        Perm.PUBLISHING_VIEW,
        Perm.ANALYTICS_VIEW,
        Perm.RECOMMENDATIONS_VIEW,
        Perm.AUTOMATION_VIEW,
    }
)

_ANALYST = _VIEWER | {
    Perm.MEMBERS_VIEW,
    Perm.RECOMMENDATIONS_MANAGE,
    Perm.USAGE_VIEW,
    Perm.ADS_VIEW,
}

_EDITOR = _VIEWER | {
    Perm.MEMBERS_VIEW,
    Perm.BRAND_EDIT,
    Perm.STRATEGY_EDIT,
    Perm.CAMPAIGN_EDIT,
    Perm.CONTENT_EDIT,
    Perm.CONTENT_SUBMIT,
    Perm.SOCIAL_VIEW,
    Perm.USAGE_VIEW,
    Perm.ADS_VIEW,
    Perm.ADS_DRAFT,
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMIN: ALL_PERMISSIONS,
    Role.EDITOR: frozenset(_EDITOR),
    Role.ANALYST: frozenset(_ANALYST),
    Role.VIEWER: _VIEWER,
}


def permissions_for(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())
