"""Metric definitions. Each platform reports its own metrics with its own definitions;
values are never summed or compared across platforms as if they were the same thing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    unit: str
    description: str
    #: Counts engagement (used to compare post performance within one platform).
    engagement: bool = False


METRICS: dict[str, MetricDefinition] = {
    d.key: d
    for d in [
        MetricDefinition(
            "views", "Views", "count", "Times the post was viewed (platform-defined)."
        ),
        MetricDefinition("impressions", "Impressions", "count", "Times the post was shown."),
        MetricDefinition("reach", "Reach", "count", "Unique accounts that saw the post."),
        MetricDefinition("clicks", "Clicks", "count", "Clicks on the post.", engagement=True),
        MetricDefinition(
            "reactions", "Reactions", "count", "Likes and other reactions.", engagement=True
        ),
        MetricDefinition("likes", "Likes", "count", "Likes on the post.", engagement=True),
        MetricDefinition("comments", "Comments", "count", "Comments on the post.", engagement=True),
        MetricDefinition(
            "shares", "Shares", "count", "Times the post was shared.", engagement=True
        ),
        MetricDefinition("saves", "Saves", "count", "Times the post was saved.", engagement=True),
        MetricDefinition(
            "engagements",
            "Engagements",
            "count",
            "Total interactions (platform-defined).",
            engagement=True,
        ),
    ]
}

#: Preferred engagement metric per platform for within-platform comparisons.
PRIMARY_ENGAGEMENT: dict[str, tuple[str, ...]] = {
    "facebook": ("reactions", "clicks", "engagements"),
    "instagram": ("likes", "comments", "engagements"),
    "tiktok": ("likes", "engagements"),
}


def definition(key: str) -> MetricDefinition:
    return METRICS.get(key) or MetricDefinition(key, key.replace("_", " ").title(), "count", "")
