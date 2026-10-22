"""Industry presets: starting suggestions, never facts about a specific business.

Presets pre-fill onboarding choices and give the AI generic, clearly-labelled
industry context. They are configuration, not per-industry code paths.
"""

from typing import TypedDict


class IndustryPreset(TypedDict):
    key: str
    label: str
    suggested_goals: list[str]
    suggested_platforms: list[str]
    example_audiences: list[str]
    content_themes: list[str]
    compliance_notes: list[str]


GOALS: dict[str, str] = {
    "awareness": "Increase brand awareness",
    "engagement": "Grow engagement with existing followers",
    "followers": "Grow follower count",
    "traffic": "Drive website traffic",
    "leads": "Generate leads or enquiries",
    "sales": "Drive sales or bookings",
    "foot_traffic": "Increase visits to a physical location",
    "retention": "Retain and re-engage existing customers",
    "launch": "Launch a new product or service",
    "reputation": "Build trust and reputation",
}

PLATFORMS: dict[str, str] = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
}

INDUSTRY_PRESETS: list[IndustryPreset] = [
    {
        "key": "restaurant",
        "label": "Restaurant, café, or food service",
        "suggested_goals": ["foot_traffic", "awareness", "retention"],
        "suggested_platforms": ["instagram", "tiktok", "facebook"],
        "example_audiences": [
            "Local residents within a short drive",
            "Office workers nearby at lunch",
        ],
        "content_themes": [
            "Behind the scenes",
            "Menu highlights",
            "Seasonal specials",
            "Team stories",
        ],
        "compliance_notes": ["Avoid unverified health or allergen claims."],
    },
    {
        "key": "retail",
        "label": "Retail store",
        "suggested_goals": ["sales", "foot_traffic", "awareness"],
        "suggested_platforms": ["instagram", "facebook", "tiktok"],
        "example_audiences": ["Local shoppers", "Gift buyers"],
        "content_themes": ["New arrivals", "Product how-tos", "Styling ideas", "Store events"],
        "compliance_notes": ["Price and discount claims must be accurate and current."],
    },
    {
        "key": "ecommerce",
        "label": "E-commerce",
        "suggested_goals": ["sales", "traffic", "retention"],
        "suggested_platforms": ["instagram", "tiktok", "facebook"],
        "example_audiences": ["Online shoppers interested in the category", "Repeat customers"],
        "content_themes": ["Product demos", "Customer use cases", "Unboxing", "Comparisons"],
        "compliance_notes": [
            "Disclose paid partnerships; keep shipping and return claims accurate."
        ],
    },
    {
        "key": "professional_services",
        "label": "Professional services (consulting, legal, accounting, agencies)",
        "suggested_goals": ["leads", "reputation", "awareness"],
        "suggested_platforms": ["facebook", "instagram"],
        "example_audiences": ["Small business owners", "Decision makers in target sectors"],
        "content_themes": ["Expert tips", "Common mistakes", "Case studies", "Team expertise"],
        "compliance_notes": [
            "Avoid guarantees of outcomes; follow professional advertising rules for your field."
        ],
    },
    {
        "key": "real_estate",
        "label": "Real estate",
        "suggested_goals": ["leads", "reputation", "awareness"],
        "suggested_platforms": ["instagram", "facebook", "tiktok"],
        "example_audiences": ["First-time buyers", "Sellers in the service area", "Investors"],
        "content_themes": [
            "Property tours",
            "Neighbourhood guides",
            "Market updates",
            "Buyer tips",
        ],
        "compliance_notes": [
            "Follow fair-housing and local advertising rules; listing details must be accurate."
        ],
    },
    {
        "key": "fitness",
        "label": "Fitness, gym, or wellness",
        "suggested_goals": ["leads", "retention", "engagement"],
        "suggested_platforms": ["instagram", "tiktok", "facebook"],
        "example_audiences": ["Beginners starting a routine", "Members wanting accountability"],
        "content_themes": ["Workout tips", "Member stories", "Class schedules", "Coach spotlights"],
        "compliance_notes": [
            "Avoid medical claims and guaranteed results; testimonials must be genuine."
        ],
    },
    {
        "key": "hospitality",
        "label": "Hospitality and travel (hotels, tours, venues)",
        "suggested_goals": ["sales", "awareness", "reputation"],
        "suggested_platforms": ["instagram", "tiktok", "facebook"],
        "example_audiences": ["Leisure travellers", "Event planners", "Local staycationers"],
        "content_themes": ["Experiences", "Local guides", "Guest moments", "Seasonal offers"],
        "compliance_notes": ["Prices, availability, and amenities must be accurate."],
    },
    {
        "key": "beauty",
        "label": "Beauty and personal care (salons, spas, clinics)",
        "suggested_goals": ["sales", "retention", "engagement"],
        "suggested_platforms": ["instagram", "tiktok", "facebook"],
        "example_audiences": ["Local clients booking regularly", "Special-occasion clients"],
        "content_themes": ["Before and after (with consent)", "Care tips", "Team work", "Offers"],
        "compliance_notes": ["Obtain consent for client images; avoid unproven treatment claims."],
    },
    {
        "key": "education",
        "label": "Education and training",
        "suggested_goals": ["leads", "reputation", "awareness"],
        "suggested_platforms": ["facebook", "instagram", "tiktok"],
        "example_audiences": ["Prospective students", "Parents", "Career changers"],
        "content_themes": ["Learning tips", "Student success", "Course previews", "Events"],
        "compliance_notes": ["Do not guarantee grades, jobs, or salaries."],
    },
    {
        "key": "other",
        "label": "Other",
        "suggested_goals": ["awareness", "engagement"],
        "suggested_platforms": ["instagram", "facebook"],
        "example_audiences": [],
        "content_themes": ["Behind the scenes", "Customer stories", "Tips", "Announcements"],
        "compliance_notes": [],
    },
]

PRESETS_BY_KEY: dict[str, IndustryPreset] = {p["key"]: p for p in INDUSTRY_PRESETS}
INDUSTRY_CHOICES = [(p["key"], p["label"]) for p in INDUSTRY_PRESETS]
