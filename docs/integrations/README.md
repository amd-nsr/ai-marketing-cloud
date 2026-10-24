# Social platform integrations: status and setup

Milestones are tracked separately on purpose; code that passes tests against stubbed APIs
is **not** the same as a verified integration.

| Milestone | Facebook Pages | Facebook Ads | Instagram (professional) | TikTok |
| --- | :-: | :-: | :-: | :-: |
| Code implemented | ✓ | ✓ (create, activate, pause, budget, sync) | ✓ (photo/carousel) | ✓ (photo posts) |
| Tests with stubbed API pass | ✓ | ✓ | ✓ | ✓ |
| App credentials configured | ✗ | ✗ | ✗ | ✗ |
| Real connect + publish/create tested | ✗ | ✗ | ✗ | ✗ |
| Platform review / audit completed | ✗ | ✗ | ✗ | ✗ |

Documentation reviewed: 2026-10-24 (Meta Graph API and Marketing API v26.0, TikTok Content
Posting API v2). Everything above "App credentials" was verified with stubbed responses and
the labelled simulation only. **Nothing has been published to Facebook or created in an ad
account, and no money has been spent.**

## Meta (Facebook Pages and Facebook Ads)

How it works ([ADR 0014](../decisions/0014-meta-integration-and-ads.md)):
1. Someone signs in with Facebook (Social accounts → Facebook Page → Connect).
2. They see the permissions they granted and declined, and the Pages and ad accounts
   available to them.
3. They choose what to connect.

Pages publish through the existing publishing engine. Ad accounts sync campaigns and spend,
and ad changes run only through the automation policy engine.

### Meta developer setup (needs your Meta account)
1. Create an app at developers.facebook.com (type **Business**). Add **Facebook Login for
   Business** (or Facebook Login) and, for ads, **Marketing API**.
2. Valid OAuth redirect URI: `<FRONTEND_URL>/oauth/callback`, e.g.
   `http://localhost:3000/oauth/callback` in development.
3. App settings → Advanced:
   - **Deauthorize callback URL:** `<API_ORIGIN>/api/v1/meta/deauthorize/`
   - **Data deletion request URL:** `<API_ORIGIN>/api/v1/meta/data-deletion/`. People are
     sent to `<FRONTEND_URL>/meta/data-deletion/<code>` to see the status.
4. Webhooks (optional, recommended for ads):
   - Callback URL: `<API_ORIGIN>/api/v1/meta/webhooks/`
   - Verify token: the value of `META_WEBHOOK_VERIFY_TOKEN`
   - Subscribe to `ad_account` (e.g. `with_issues_ad_objects`) and, if available, `user`
     `permissions`.
5. Environment variables:

| Variable | Purpose |
| --- | --- |
| `META_APP_ID`, `META_APP_SECRET` | App credentials. The secret also signs `appsecret_proof` and verifies callbacks. |
| `META_GRAPH_VERSION` | Pinned API version (default `v26.0`). |
| `META_ADS_ENABLED` | Request the ads permissions and show ad accounts (default off; on in development). |
| `META_WEBHOOK_VERIFY_TOKEN` | Random string you also enter in the webhook setup. |
| `META_USAGE_THROTTLE_PERCENT` | Pause calls when Meta reports usage at or above this (default 90). |
| `META_TOKEN_WARNING_DAYS` | Warn before a Meta login expires (default 7). |
| `ADS_INSIGHTS_DAYS` | Days of daily insights per sync (default 30). |
| `ADS_SPEND_DATA_MAX_AGE_HOURS` | Spend-affecting changes need spend synced within this window (default 24). |

### Permissions requested (only for enabled features)

| Feature | Permissions | Review needed |
| --- | --- | --- |
| Publish to Pages, read post insights | `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `read_insights` | App Review (Advanced Access) |
| Read ad accounts, campaigns, insights | `ads_read` | App Review; business verification |
| Create, activate, pause, change budgets | `ads_management` | App Review (Advanced Access); business verification |

In development mode only people with a role on the Meta app can connect, and only to
Pages and ad accounts they manage. **Production use requires App Review of each
permission and business verification for the ads permissions.** These can't be done
from the code.

### Real-account validation checklist (not done yet)
1. Connect as someone with a role on the app. Check that granted and declined permissions
   match the consent screen, and that more than 25 Pages paginate.
2. Connect one Page and publish an approved text post and a photo post. Confirm both on
   the Page; metrics appear after the next collection.
3. Connect an ad account. Run **Sync now** and compare campaigns, statuses, budgets and
   yesterday's spend with Ads Manager.
4. Set the advertising limits. Create a draft with a **1.00/day** budget and approve it.
   Create it on Meta and confirm the campaign, ad set, creative and ad all exist and are
   **paused**.
5. Activate the campaign briefly, then pause it. Confirm status changes in Ads Manager and
   that spend appears in the next sync.
6. Remove the app on Facebook (Settings → Business integrations). The connection must show
   "Access removed" and its assets disconnected.
7. Trigger a data-deletion request from the same settings page and open the status link.

Known gaps:
- Objectives: Traffic, Awareness and Engagement.
- Targeting: countries and age only (no interests or custom audiences).
- Link ads with an optional image; no video, carousel ads, Reels or Stories.
- Campaign budget (CBO) with a daily budget only.
- Insights are daily at campaign level, read synchronously (no async report jobs for very
  large accounts).

## Facebook Pages (publishing details)
Uses the Meta setup above.

Supported: text/link posts, single photo, multi-photo posts. Not supported yet: Reels,
Stories, video.

## Instagram (professional accounts)
Uses the same Meta app with Facebook Login. Additional permissions:
`instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`.
Requirements: an Instagram **professional** account linked to a Facebook Page; images must
be **JPEG**; Instagram fetches media from a **public URL**, so `STORAGE_BACKEND=s3` is
required (signed URLs). Limit: 100 API posts per 24 hours. Not supported yet: Reels,
Stories.

## TikTok
1. Create an app at developers.tiktok.com with **Login Kit** and **Content Posting API**
   (Direct Post); redirect URI `<FRONTEND_URL>/oauth/callback`.
2. Scopes: `user.info.basic`, `video.publish`, `video.list`.
3. Verify the domain/URL prefix that serves media (`PULL_FROM_URL` requires it).
4. Set `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`.
5. **Until TikTok audits the app, all posts are private (SELF_ONLY).** The integration
   reads the creator's allowed privacy levels and never claims public posting it can't do.

Supported: photo posts. Not supported yet: video upload, metrics.
