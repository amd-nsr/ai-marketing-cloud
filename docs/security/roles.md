# Roles and permissions

Source of truth: `backend/apps/organizations/roles.py`. Enforced on the server for
every organization-scoped request (`OrganizationScopedMixin`). The frontend only uses
permissions to hide controls a member cannot use.

| Permission | Owner | Admin | Editor | Analyst | Viewer |
| --- | :-: | :-: | :-: | :-: | :-: |
| `org.view` — see the organization | ✓ | ✓ | ✓ | ✓ | ✓ |
| `org.manage` — rename, organization settings | ✓ | ✓ | | | |
| `members.view` — list members | ✓ | ✓ | ✓ | ✓ | |
| `members.manage` — invite, change roles, remove | ✓ | ✓ | | | |
| `brand.view` / `brand.edit` — business profile & brand | ✓/✓ | ✓/✓ | ✓/✓ | ✓/– | ✓/– |
| `strategy.view` / `strategy.edit` — marketing plans | ✓/✓ | ✓/✓ | ✓/✓ | ✓/– | ✓/– |
| `campaign.view` / `campaign.edit` | ✓/✓ | ✓/✓ | ✓/✓ | ✓/– | ✓/– |
| `content.view` / `content.edit` / `content.submit` | ✓ | ✓ | ✓ | view | view |
| `content.approve` — approve/reject content | ✓ | ✓ | | | |
| `social.view` — see connected accounts | ✓ | ✓ | ✓ | | |
| `social.manage` — connect/disconnect accounts | ✓ | ✓ | | | |
| `publishing.view` — publishing history | ✓ | ✓ | ✓ | ✓ | ✓ |
| `publishing.publish` — publish/schedule to social accounts | ✓ | ✓ | | | |
| `analytics.view` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `recommendations.view` / `recommendations.manage` | ✓/✓ | ✓/✓ | ✓/– | ✓/✓ | ✓/– |
| `automation.view` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `automation.manage` — autonomy mode, policies, pause | ✓ | ✓ | | | |
| `automation.approve` — approve automated actions | ✓ | ✓ | | | |
| `usage.view` — AI usage and quotas | ✓ | ✓ | ✓ | ✓ | |
| `audit.view` — audit log | ✓ | ✓ | | | |
| `ads.view` — ad accounts, campaigns, ad performance | ✓ | ✓ | ✓ | ✓ | |
| `ads.draft` — create and edit campaign drafts (incl. AI drafts) | ✓ | ✓ | ✓ | | |
| `ads.manage` — approve drafts, create on Meta, activate, pause, change budgets, connect ad accounts | ✓ | ✓ | | | |

Additional rules (in `organizations/services.py`):

- Only an **owner** can grant, remove, or invite the owner role. Admins cannot.
- An organization always keeps **at least one owner** (demote/remove/leave blocked).
- Any member may **leave** an organization (subject to the last-owner rule).
- Invitations are bound to an email address: only a signed-in user with that email can
  accept. They expire after 7 days; one pending invitation per email per organization.

Non-members receive **404** (not 403) for every organization-scoped URL, so the API
does not reveal whether another tenant's organization or objects exist.
