# 0014 — Meta integration: shared layer, Page selection, paid ads under policy

**Status:** Accepted (2026-10-24). **Changes scope:** the master plan excluded paid
advertising from the MVP ("Do not automatically change advertising budgets or spend money
in the MVP"). At the product owner's request this decision adds Facebook Ads. Spending
stays behind deterministic limits and explicit approvals, and AI never calls Meta.

## Decision

**One Meta layer (`apps.meta`).** All Graph and Marketing API calls go through
`GraphClient`:
- versioned (`META_GRAPH_VERSION`), with `appsecret_proof` on every token-bearing call;
- cursor pagination;
- throttling from Meta's usage headers (`X-App-Usage`, `X-Business-Use-Case-Usage`,
  `X-Ad-Account-Usage`) before limits are hit;
- errors mapped onto the existing integration error types (reconnect, permission missing,
  rate limited, transient, rejected, uncertain).

Facebook, Instagram and Ads code calls this client and never builds Graph URLs.

**A Meta login is its own record (`MetaConnection`):**
- It holds the encrypted long-lived user token, and the permissions actually *granted* and
  *declined* (`/me/permissions`), not the ones requested.
- It stores the assets it discovered (Pages, ad accounts), with non-secret fields only.
- Nothing is connected automatically: the person selects Pages (stored as `SocialAccount`
  rows with their own Page tokens) and ad accounts (`AdAccount`).
- Scopes are requested per enabled feature. Ads scopes (`ads_read`, `ads_management`) only
  when `META_ADS_ENABLED`.

**Lifecycle:**
- Disconnecting revokes the app's permissions on Meta (`DELETE /me/permissions`) and
  detaches everything chosen through the login. A failed revoke is reported, and the local
  disconnect still completes.
- A daily task warns before user tokens expire, marks expired or revoked logins for
  reconnection, and pauses assets whose permissions were removed.
- Meta's deauthorize and data-deletion callbacks (signed requests, HMAC verified) revoke
  everywhere and delete Meta-derived data. They return a confirmation code and a public
  status page.
- Webhooks are signature-verified (`X-Hub-Signature-256`): `ad_account` changes trigger a
  sync, and `user` `permissions` changes trigger a permissions refresh.

**Ads (`apps.ads`) behind an internal interface.** `AdsPlatform` has a Meta implementation
(Marketing API) and a labelled simulation, so business logic doesn't depend on Meta.
- **Mirror:** campaigns, ad sets, ads and daily campaign insights. Money is stored in
  major units, converted to Meta minor units only at the boundary; missing metrics are
  NULL. Sync steps fail independently (partial status).
- **Drafts:** made by hand or by AI (the existing workflow system, schema-validated
  output). They are validated deterministically (objective, budget, targeting, special ad
  categories, creative, Page, link, schedule) and approved per revision; edits require
  re-approval.
- **Writes:** create (campaign, then ad set, image, creative, ad, all PAUSED), activate
  (children first, campaign last), pause, and daily budget change. Each write is an
  `AutomationAction` evaluated by the policy engine, for people as well as automation.
  Creation saves each Meta id as it is created. A retry resumes from the failed step; a
  lost response is recovered by looking up a name tag before anything is re-created.
- **Hard limits (`AutomationPolicy`, in code):**
  - Limits: currency, maximum daily budget per campaign, maximum total daily budget across
    running campaigns, monthly spend limit, and maximum budget increase per change.
  - Any spend-affecting change is refused when a limit is missing, the account's currency
    differs, or spend data is older than `ADS_SPEND_DATA_MAX_AGE_HOURS`.
  - The ads kill switch blocks everything except pausing.
  - Automation never creates campaigns. Each automated change type (pause, budget,
    activate) must be enabled separately, and needs approval in semi-automatic mode.
- **Recommendations** are deterministic rules (spend guard, no-click pause, budget-limited
  winner), proposed as actions with their evidence. Nothing writes outside the engine.

## Consequences
- Real Meta use needs a Meta app with Facebook Login and the Marketing API. App Review
  covers `pages_*`, `read_insights` and `ads_*`; business verification and Advanced Access
  are needed for `ads_management` beyond the app's own roles. None of this exists yet, so
  the real integration is **unverified** (see `docs/integrations/README.md`).
- Only campaign-budget (CBO) campaigns with a daily budget are managed by limits. Campaigns
  created elsewhere without a campaign-level daily budget can be viewed and paused but not
  activated or re-budgeted here.
- Instagram still connects through its own flow; moving it onto `MetaConnection` is a
  follow-up.
