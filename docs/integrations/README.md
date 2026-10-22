# Social platform integrations: status and setup

Milestones are tracked separately on purpose; code that passes tests against stubbed APIs
is **not** the same as a verified integration.

| Milestone | Facebook Pages | Instagram (professional) | TikTok |
| --- | :-: | :-: | :-: |
| Code implemented | ✓ | ✓ (photo/carousel) | ✓ (photo posts) |
| Tests with stubbed API pass | ✓ | ✓ | ✓ |
| App credentials configured | ✗ | ✗ | ✗ |
| Real connect + publish tested | ✗ | ✗ | ✗ |
| Platform review / audit completed | ✗ | ✗ | ✗ |

Documentation reviewed: 2026-10-20 (Meta Graph API v26.0, TikTok Content Posting API v2).

## Facebook Pages (first real integration)
1. Create an app at developers.facebook.com (type "Business"); add **Facebook Login**.
2. Valid OAuth redirect URI: `<FRONTEND_URL>/oauth/callback` (e.g.
   `http://localhost:3000/oauth/callback` in development).
3. Permissions requested: `pages_show_list`, `pages_manage_posts`,
   `pages_read_engagement`, `read_insights`.
4. Set `META_APP_ID`, `META_APP_SECRET` (and optionally `META_GRAPH_VERSION`).
5. In development mode only people with a role on the app (admins, developers, testers)
   can connect. Production use requires **App Review** of the permissions above.
6. Test: Social accounts → Facebook Page → Connect → choose a Page → publish an approved
   text post → confirm it appears on the Page and its permalink opens.

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
