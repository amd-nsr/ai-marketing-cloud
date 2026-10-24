export interface NavItem {
  label: string;
  /** Path relative to /o/[orgId]. */
  href: string;
  /** Hidden from the menu when the member lacks this permission (server still enforces). */
  permission?: string;
  section: "Plan" | "Create" | "Publish" | "Measure" | "Organization";
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "", section: "Plan" },
  { label: "Strategy", href: "/strategy", permission: "strategy.view", section: "Plan" },
  { label: "Business & brand", href: "/brand", permission: "brand.view", section: "Plan" },
  { label: "Campaigns", href: "/campaigns", permission: "campaign.view", section: "Plan" },
  { label: "Content studio", href: "/content", permission: "content.view", section: "Create" },
  { label: "Calendar", href: "/calendar", permission: "content.view", section: "Create" },
  { label: "Approvals", href: "/approvals", permission: "content.view", section: "Create" },
  { label: "Publishing", href: "/publishing", permission: "publishing.view", section: "Publish" },
  { label: "Social accounts", href: "/accounts", permission: "social.view", section: "Publish" },
  { label: "Ads", href: "/ads", permission: "ads.view", section: "Publish" },
  { label: "Analytics", href: "/analytics", permission: "analytics.view", section: "Measure" },
  {
    label: "Recommendations",
    href: "/recommendations",
    permission: "recommendations.view",
    section: "Measure",
  },
  {
    label: "Automation",
    href: "/automation",
    permission: "automation.view",
    section: "Organization",
  },
  {
    label: "Operations",
    href: "/operations",
    permission: "org.manage",
    section: "Organization",
  },
  { label: "Settings", href: "/settings", permission: "org.view", section: "Organization" },
  {
    label: "Audit log",
    href: "/settings/audit",
    permission: "audit.view",
    section: "Organization",
  },
];

export const NAV_SECTIONS: NavItem["section"][] = [
  "Plan",
  "Create",
  "Publish",
  "Measure",
  "Organization",
];
