"""Which Meta permissions each feature needs. Request only what the deployment uses.

Permissions are granted per person during Facebook Login and can be declined or removed
later, so features check the permissions recorded on the connection (refreshed from
``/me/permissions``), not the ones we asked for.
"""

from django.conf import settings

PAGES_FEATURE = "pages"
ADS_READ_FEATURE = "ads_read"
ADS_WRITE_FEATURE = "ads_write"

FEATURE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    # List Pages, publish to them, read engagement and post insights.
    PAGES_FEATURE: (
        "pages_show_list",
        "pages_manage_posts",
        "pages_read_engagement",
        "read_insights",
    ),
    # Read ad accounts, campaigns and insights.
    ADS_READ_FEATURE: ("ads_read",),
    # Create campaigns and change their status or budget.
    ADS_WRITE_FEATURE: ("ads_read", "ads_management"),
}

FEATURE_LABELS = {
    PAGES_FEATURE: "Publish to Facebook Pages and read post insights",
    ADS_READ_FEATURE: "Read ad accounts, campaigns and ad performance",
    ADS_WRITE_FEATURE: "Create campaigns, activate, pause and change budgets",
}


def enabled_features() -> list[str]:
    features = [PAGES_FEATURE]
    if settings.META_ADS_ENABLED:
        features += [ADS_READ_FEATURE, ADS_WRITE_FEATURE]
    return features


def requested_scopes() -> list[str]:
    scopes: list[str] = []
    for feature in enabled_features():
        for scope in FEATURE_PERMISSIONS[feature]:
            if scope not in scopes:
                scopes.append(scope)
    return scopes


def feature_status(granted: list[str]) -> list[dict[str, object]]:
    """Per enabled feature: whether every permission it needs was granted."""
    have = set(granted)
    return [
        {
            "feature": f,
            "label": FEATURE_LABELS[f],
            "available": set(FEATURE_PERMISSIONS[f]) <= have,
            "missing": [p for p in FEATURE_PERMISSIONS[f] if p not in have],
        }
        for f in enabled_features()
    ]


def has_feature(granted: list[str], feature: str) -> bool:
    return set(FEATURE_PERMISSIONS[feature]) <= set(granted)
