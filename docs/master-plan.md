import pypandoc

markdown = r"""# Master Engineering Plan: AI Marketing Cloud

## 1. Role and Mission

Act as the lead software architect, senior full-stack engineer, AI systems engineer, and technical product partner responsible for designing and building a production-oriented SaaS platform from scratch.

Translate the product vision into maintainable, secure, testable software. Implement incrementally, validate functionality with automated tests, keep the application runnable, avoid unnecessary complexity, and report accurately what is implemented, tested, simulated, or externally unverified.

Do not attempt to build the entire long-term product in one pass. Establish the foundation, deliver working vertical slices, and expand in controlled phases.

The product owner has a backend and data engineering background, including Python, Django, REST APIs, PostgreSQL, Redis, Celery, Docker, data pipelines, and AI integrations. Technical explanations may be detailed, but implementation choices should remain pragmatic and business-focused.

---

## 2. Product Vision

Build an **AI Marketing Cloud**: a multi-tenant SaaS platform that helps businesses plan, create, manage, publish, measure, and improve their marketing activities from one workspace.

The long-term ambition is to reduce dependence on fragmented marketing tools and repetitive agency work through AI-enabled strategy, content creation, social publishing, analytics, and increasingly autonomous execution.

The platform should help a business owner answer:

- What should my business focus on in its marketing?
- Who am I targeting, and what should I communicate?
- What content should I create this week?
- How should a campaign be adapted for Instagram, TikTok, and Facebook?
- What should be published, and when?
- Which activities are performing well?
- What should change based on actual results?
- Which tasks can run automatically, and which require approval?

### 2.1 Initial target market

Do not lock the product into one industry. Design a reusable core that can serve retail, restaurants, professional services, e-commerce, real estate, fitness, hospitality, and other small and medium-sized businesses.

Do not build specialized workflows for every industry in the MVP. Use configurable business profiles, audience definitions, brand guidelines, marketing objectives, campaign templates, and industry presets.

Validate the product with real businesses before investing heavily in vertical-specific features.

### 2.2 Long-term direction

The initial product is exclusively focused on AI Marketing Cloud.

Potential future expansions include:

- Financial planning and analysis (FP&A).
- Cash-flow forecasting and financial insights.
- Business performance monitoring.
- Cross-functional AI workflows.
- A broader AI Business Operating Platform.

These future capabilities must not distract from the initial marketing product. Keep the architecture extensible, but do not create FP&A modules or unrelated business applications in the MVP.

### 2.3 Product principles

1. Business outcomes before technical novelty.
2. Working workflows before broad feature coverage.
3. AI as a controlled capability, with policy-governed execution.
4. Human control remains available: users can edit, reject, approve, pause, and override.
5. Multi-tenancy from day one.
6. Provider independence for AI models and social platforms.
7. Explicit permissions for consequential actions.
8. Reliable scheduling, retries, publishing, and automation.
9. Incremental delivery with verification at each phase.
10. No fake integrations: label mocks and simulations clearly.

---

## 3. Mandatory Repository Architecture

Create a new project from scratch.

Use **one Git repository with separate top-level `frontend/` and `backend/` directories**. The applications must have separate dependencies, build processes, tests, configurations, and deployment artifacts.

```text
ai-marketing-cloud/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── layout/
│   │   │   └── features/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   ├── auth/
│   │   │   └── validation/
│   │   ├── types/
│   │   └── styles/
│   ├── public/
│   ├── tests/
│   ├── package.json
│   └── ...
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── accounts/
│   │   ├── organizations/
│   │   ├── brand/
│   │   ├── marketing/
│   │   ├── content/
│   │   ├── social/
│   │   ├── publishing/
│   │   ├── analytics/
│   │   ├── ai/
│   │   ├── automation/
│   │   ├── notifications/
│   │   └── usage/
│   ├── tests/
│   ├── manage.py
│   ├── pyproject.toml
│   └── ...
├── infrastructure/
│   ├── docker/
│   ├── deployment/
│   ├── scripts/
│   └── ...
├── docs/
│   ├── architecture/
│   ├── decisions/
│   ├── api/
│   ├── security/
│   ├── development/
│   └── product/
├── .github/
│   └── workflows/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Makefile
└── README.md
```

This is a starting structure, not a requirement to create empty directories or implement every domain immediately. Add modules when their corresponding features are needed.

### Repository rules

- `frontend/` must not import Python backend modules or backend implementation details.
- `backend/` must not contain frontend source code.
- The frontend communicates with the backend through documented HTTP APIs.
- Keep Node dependencies in the frontend and Python dependencies in the backend.
- Keep secrets out of source control.
- Use a root-level development orchestration file where practical.
- Make frontend and backend independently buildable and deployable.
- Document the API contract; use OpenAPI generated from Django REST Framework where practical.
- Do not introduce a shared-code package unless there is a concrete need.
- Share API schemas through generated or explicitly maintained contracts, not runtime coupling.
- Keep infrastructure configuration separate from business logic.
- Do not split into multiple Git repositories at the beginning. Independent deployment does not require separate repositories.

---

## 4. Technology Stack

Use this baseline unless repository constraints or a demonstrable technical reason justify a change. Select compatible, stable versions during implementation and document them.

### 4.1 Frontend

- Next.js with TypeScript.
- React.
- Accessible, consistent UI components.
- Tailwind CSS or a similarly maintainable styling system.
- Typed HTTP client for the backend API.
- Consistent schema-based form validation.
- Appropriate server/client component boundaries.
- Responsive desktop, tablet, and mobile layouts.
- Automated frontend tests.

Do not put secret-bearing AI or social-platform calls directly in the browser.

### 4.2 Backend

- Python.
- Django.
- Django REST Framework.
- PostgreSQL.
- Redis.
- Celery for asynchronous and scheduled work.
- Django migrations.
- OpenAPI documentation.
- A consistent testing approach, such as pytest with Django support.
- Structured logging and centralized exception handling.

Use Django for authentication, permissions, ORM, migrations, administration, and domain-oriented business applications.

### 4.3 Background processing

Run Celery workers and the scheduler as separate processes using the same backend codebase.

Use asynchronous jobs for:

- AI generation when it may take significant time.
- Media processing.
- Publishing and scheduled publishing.
- Social-account synchronization.
- Analytics collection.
- Retryable external API operations.
- Notifications.
- Usage aggregation.

Do not create a separate microservice for every worker category. Use Celery Beat or another explicitly selected scheduling mechanism, and avoid duplicate schedulers dispatching the same work.

### 4.4 Storage

- PostgreSQL for structured application data.
- Redis for Celery infrastructure, caching, and suitable short-lived coordination.
- Object storage for uploaded media and generated assets in production.
- Local or S3-compatible storage for development as appropriate.

Do not store large media binaries directly in relational database rows.

### 4.5 Infrastructure

- Docker and Docker Compose for local development.
- Separate production configuration.
- Environment-driven settings.
- A documented cloud deployment process.
- CI for linting, type checking, tests, and builds.
- Secure secret injection in production.

Do not require Kubernetes for the MVP.

---

## 5. System Architecture

Build a modular monolith initially, with independently runnable application processes.

```text
User
  |
  v
Next.js Frontend
  |
  | HTTPS / JSON API
  v
Django REST API
  |
  +-- Identity and Organizations
  +-- Brand and Business Context
  +-- Marketing Strategy
  +-- Content and Creative Management
  +-- Social Integrations
  +-- Publishing Workflows
  +-- Analytics and Recommendations
  +-- AI Provider Abstraction
  +-- Automation Policy Engine
  +-- Usage and Audit
  |
  +--> PostgreSQL
  |
  +--> Redis / Celery Queue
             |
             v
       Celery Workers
             |
             +--> AI Providers
             +--> Instagram APIs
             +--> TikTok APIs
             +--> Facebook APIs
             +--> Object Storage
```

The frontend, API, and workers are separate runtime processes. They may share a repository and backend codebase without being the same deployable process.

### Architectural rules

1. Keep business logic in domain services, not directly in views or serializers.
2. Keep external integrations behind interfaces or adapters.
3. Use database transactions for operations requiring consistency.
4. Use background jobs for long-running or retryable work.
5. Make external actions idempotent wherever possible.
6. Separate user-facing request latency from long-running AI and publishing tasks.
7. Keep authorization checks close to protected domain operations.
8. Do not add Kafka, Kubernetes, microservices, or distributed orchestration without a demonstrated need.
9. Use explicit state transitions for publishing and automation workflows.
10. Document major architectural decisions in short architecture decision records (ADRs).

---

## 6. Multi-Tenant Identity and Authorization

Tenant isolation is a foundational security requirement, not a later enhancement.

### 6.1 Core entities

Implement an appropriate model for:

- User.
- Organization.
- OrganizationMembership.
- OrganizationRole or equivalent permissions.
- AuditEvent.

A user may belong to multiple organizations.

Suggested initial roles:

- Owner.
- Admin.
- Editor.
- Analyst.
- Viewer.

Define and document the exact permissions of each role. An Analyst, for example, must not automatically receive publishing or integration-management permissions.

### 6.2 Security requirements

- Use Django's supported authentication facilities and a secure session or token strategy appropriate for deployment.
- Protect state-changing operations against CSRF when cookie-based authentication is used.
- Enforce authentication and authorization on the server.
- Validate organization membership on every organization-scoped operation.
- Never trust a client-supplied organization ID without checking access.
- Scope all queries and mutations to authorized organizations.
- Test direct-object-reference attacks and cross-tenant access.
- Rate-limit sensitive endpoints.
- Use secure cookie settings and HTTPS in production.
- Protect password reset and account recovery flows.
- Store integration credentials securely.
- Do not expose access tokens or secret configuration to the frontend.
- Log security events without logging secrets.

Do not rely solely on frontend navigation restrictions to enforce access control.

---

## 7. Core Domain Model

Implement these entities incrementally as features require them.

### Foundation

- User.
- Organization.
- OrganizationMembership.
- AuditEvent.

### Business and brand

- BusinessProfile.
- IndustryProfile or configurable industry attributes.
- TargetAudience.
- BrandGuideline.
- BrandAsset.
- BrandVoiceExample.

### Marketing

- MarketingPlan.
- MarketingObjective.
- Campaign.
- CampaignChannel.
- ContentItem.
- ContentVersion.
- ContentAsset.
- Approval.

### Social and publishing

- SocialConnection.
- SocialAccount.
- PlatformCapability.
- PublishingJob.
- PublishedPost.
- PublishingAttempt.
- WebhookEvent, where applicable.

### Analytics

- MetricSnapshot.
- AnalyticsReport or equivalent.
- MarketingRecommendation.
- RecommendationEvidence.

### AI and automation

- AIProviderConfiguration.
- AIUsageRecord.
- AIWorkflowRun.
- AutomationPolicy.
- AutomationAction.
- AutomationApproval.

### Commercial and operational

- UsageAllowance or UsageLedger.
- Notification.
- Billing-related models only when the billing phase begins.

### Data-model rules

- Use UUIDs or another deliberate identifier strategy consistently.
- Include created and updated timestamps where appropriate.
- Add organization ownership to tenant-scoped records.
- Add database indexes for common query patterns.
- Add uniqueness constraints where duplicates would be harmful.
- Use migrations for every schema change.
- Use explicit statuses for complex workflows instead of loosely interpreted booleans.
- Store external platform identifiers and synchronization metadata.
- Use soft deletion only when retention and restoration requirements justify it.
- Define retention and deletion behavior for customer content, tokens, generated assets, and analytics.

Do not implement every model immediately. Build the smallest coherent data model for each phase.

---

## 8. Business Onboarding and Brand Context

Create an onboarding flow that collects enough information for useful marketing output without making setup unnecessarily difficult.

Collect:

- Business name.
- Industry.
- Website, if available.
- Business description.
- Products or services.
- Location and service area, when relevant.
- Target audience.
- Main marketing goals.
- Preferred platforms.
- Brand tone and communication style.
- Preferred language or languages.
- Relevant restrictions and claims that must not be made.
- Existing brand assets, such as logos, colors, and approved images.

Allow optional information to be skipped and completed progressively.

Support configurable industry presets, but do not hard-code the entire system around one industry.

The platform should assemble validated business context for AI workflows. Context must be organization-specific and contain only information necessary for the requested task.

Users must be able to inspect and edit important business and brand facts rather than treating AI-generated assumptions as verified facts.

---

## 9. AI Architecture

Build a provider-independent AI layer from the beginning. Do not tie business logic directly to a provider SDK or response format.

### 9.1 Provider abstraction

Create a common interface for the capabilities the product actually needs.

Potential capabilities include:

- Text generation.
- Structured output.
- Content rewriting.
- Classification.
- Summarization.
- Embeddings and retrieval, when justified.
- Image generation, if supported by the selected provider.

Do not assume every provider supports every capability. Use capability discovery or explicit configuration so unsupported operations fail clearly.

Choose the initial provider during setup based on current API capabilities, quality, cost, latency, availability, data handling, and developer access. Do not hard-code a permanent provider decision into the architecture.

### 9.2 AI service responsibilities

Centralize:

- Provider selection.
- Model configuration.
- Request validation.
- Structured-output validation.
- Timeouts.
- Retry policies.
- Usage and cost measurement.
- Error normalization.
- Logging.
- Organization-level usage limits.
- Fallback behavior where appropriate.

Avoid indiscriminate retries for invalid requests, authorization failures, or non-retryable provider errors.

Do not silently switch to a provider with different data-handling characteristics without making that behavior explicit.

### 9.3 Marketing strategist

Build a structured workflow using the business profile and brand context to produce:

- Marketing objectives.
- Audience hypotheses.
- Campaign concepts.
- Content themes.
- Suggested channel allocation.
- Content calendars.
- Proposed metrics and measurement plans.

Distinguish between facts supplied by the user, external evidence, and AI-generated assumptions. Do not guarantee marketing outcomes.

### 9.4 Content generation

Support structured generation of:

- Captions.
- Headlines and hooks.
- Calls to action.
- Hashtag suggestions.
- Short-form video scripts.
- Carousel outlines.
- Post descriptions.
- Platform-specific variants.
- Creative briefs.

Validate outputs against expected schemas. Allow users to edit and regenerate content without losing important prior versions.

### 9.5 AI workflow orchestration

Begin with ordinary service functions and explicit workflow steps.

Introduce LangGraph or another orchestration framework only if a concrete workflow requires persistent state, branching, retries, or coordinated multi-step execution that would otherwise be difficult to maintain.

Do not begin with autonomous agents communicating without strict boundaries.

Every agent or workflow must have:

- Defined inputs and outputs.
- Bounded permissions.
- Clear success and failure conditions.
- Time and usage limits.
- Traceable execution.
- A safe stopping condition.

### 9.6 AI safety and quality

- Treat uploaded documents, connected content, and retrieved material as untrusted input.
- Do not allow external instructions to override system policy or organization permissions.
- Validate structured output before execution.
- Require server-side checks before an AI-generated action reaches an external service.
- Prevent AI workflows from obtaining unrestricted access to secrets or arbitrary tools.
- Record the model and relevant configuration used for important outputs.
- Establish evaluation examples for strategy and content quality.
- Avoid fabricated business facts, unsupported performance claims, and fabricated analytics.

---

## 10. Social Platform Integrations

The initial target platforms are:

1. Instagram.
2. TikTok.
3. Facebook.

Design the shared integration architecture for all three from the beginning. Implement external API integrations incrementally.

Do not assume that a shared internal interface means identical capabilities on every platform.

### 10.1 Integration adapter

Define a shared internal contract for capabilities such as:

- Initiating account connection.
- Completing OAuth authorization.
- Retrieving available account information.
- Inspecting supported publishing capabilities.
- Validating media and content requirements.
- Submitting a publication request.
- Retrieving publication status.
- Retrieving supported metrics.
- Refreshing or revoking credentials where supported.
- Handling webhook events where available.
- Normalizing external errors and rate limits.

Platform-specific adapters must implement only capabilities that the actual provider supports.

Use a capability registry or explicit capability metadata to control which actions are available in the UI.

### 10.2 API validation

Before implementing each real integration:

- Inspect current official developer documentation.
- Confirm the appropriate APIs and OAuth flow.
- Identify required permissions and review requirements.
- Confirm eligible account types.
- Confirm supported publishing formats.
- Confirm available analytics.
- Identify development, sandbox, and production restrictions.
- Document app registration requirements.
- Identify rate limits and token lifecycle requirements.

Do not assume credentials or permissions will be granted automatically.

Do not claim an integration is production-ready until its required external flows have been verified.

### 10.3 Integration order

Start by building the shared integration contract and a clearly labeled mock adapter for local testing.

Then choose the first real platform based on validated API access, publishing feasibility, account eligibility, and business value. Do not choose solely based on popularity.

Implement and test one complete real integration, then reuse the architecture for the remaining platforms.

All three platforms should be represented in product design and data models, but launch readiness must be assessed individually.

### 10.4 Publishing reliability

A publication request must have a durable state lifecycle, for example:

- Draft.
- Awaiting approval.
- Approved.
- Scheduled.
- Queued.
- Publishing.
- Published.
- Failed.
- Cancelled.

Add appropriate transitions for platform-specific asynchronous processing.

Implement:

- Idempotency or duplicate-prevention mechanisms.
- Retry handling.
- External request identifiers.
- Error classification.
- Publishing-attempt records.
- Scheduled execution.
- Cancellation where supported.
- Reconciliation for uncertain outcomes.
- Token expiration and reconnection handling.
- Audit events.

If an external request times out after submission, do not blindly submit a second post. Determine whether the original request may have succeeded and reconcile its status where possible.

### 10.5 Media management

Support media types needed for the first vertical workflow.

Store media in object storage, record metadata in PostgreSQL, and use signed URLs or an equivalent secure delivery mechanism where required.

Validate file types, sizes, dimensions, durations, and applicable platform constraints.

Do not assume an uploaded local file can be passed directly to a social API. Implement the actual media-transfer process required by each platform.

---

## 11. Autonomy: Manual, Semi-Automatic, and Automatic

Autonomy is a central product feature.

Implement the three modes using a common workflow engine and policy-based execution layer. Do not build three separate marketing systems.

Autonomy should be configurable at organization level, with more specific workflow settings when useful.

### 11.1 Manual mode

The system may generate strategies, content, campaigns, and recommendations. The user initiates consequential actions, reviews results, and controls publishing.

### 11.2 Semi-automatic mode

The system may prepare campaigns, generate content variants, populate proposed calendars, validate content against brand guidelines, recommend scheduling, and prepare publishing jobs for approval.

Actions requiring approval remain pending until an authorized user approves them.

The approval experience must display what will happen, which account will be affected, and the content or settings that will be submitted.

### 11.3 Automatic mode

The system may execute explicitly authorized, low-risk workflows within defined policies.

Examples:

- Publishing content already approved for automatic execution.
- Publishing within an authorized schedule and account.
- Generating routine content within defined brand and content restrictions.
- Updating future recommendations from collected performance data.

Automatic mode must not grant permission for every action. Require appropriate explicit authorization for new account connections, advertising expenditure, financial commitments, sensitive public communications, and other consequential actions.

Do not automatically change advertising budgets or spend money in the MVP.

### 11.4 Automation policy engine

Before an action executes, evaluate:

1. The requesting user or initiating workflow.
2. Organization membership and permissions.
3. The current autonomy mode.
4. Workflow-specific authorization.
5. Required approvals.
6. Applicable content and brand rules.
7. Platform capabilities.
8. Scheduling and publication limits.
9. Usage and financial limits, where relevant.
10. Whether the action is already completed, pending, or cancelled.

The policy engine should return a clear decision:

- Execute.
- Await approval.
- Reject.
- Defer.
- Cancel.

### 11.5 Durable action execution

Represent significant automated actions as persistent records capturing:

- Organization.
- Action type.
- Workflow.
- Relevant resource.
- Current state.
- Applicable policy.
- Approval details.
- Creation and execution timestamps.
- Attempt count.
- Error details.
- External request or publication identifier, if available.

Use idempotency, safe retries, explicit state transitions, and audit history.

Provide a way to pause automation for an organization and cancel eligible pending work.

A setting change must not retroactively authorize actions that were previously forbidden. Re-evaluate pending actions when policy changes.

---

## 12. MVP Product Scope

Build the smallest product that demonstrates the core business value.

### Feature 1: Authentication and organizations

- Registration and login.
- Account recovery where applicable.
- Organization creation.
- Membership and roles.
- Organization switching for multi-organization users.
- Tenant-scoped authorization.

### Feature 2: Business onboarding

- Business profile.
- Industry selection.
- Target audience.
- Goals and services.
- Brand voice and guidelines.
- Logo and brand asset upload.
- Editable business context.

### Feature 3: AI marketing plan

- Generate an initial marketing plan.
- Define objectives and content themes.
- Propose campaign ideas.
- Suggest a manageable content calendar.
- Allow editing and regeneration.
- Store plan history.

### Feature 4: Content studio

- Generate captions and post copy.
- Create platform-specific variants.
- Produce content briefs and supported creative assets.
- Edit and version content.
- Organize content by campaign and channel.
- Validate required content fields.

Image generation may be included when a suitable provider and capability are configured. It must not be a dependency for the entire platform to function.

### Feature 5: Campaign and calendar management

- Create campaigns.
- Associate content with campaigns.
- View a calendar.
- Track content status.
- Submit content for approval.
- Approve, reject, edit, or cancel pending content.

### Feature 6: Social account integration and publishing

- Shared integration architecture for Instagram, TikTok, and Facebook.
- One validated real publishing integration first.
- A mock adapter for automated testing.
- Account connection management.
- Publishing status.
- Error handling and recovery.
- Incremental integration of the remaining platforms.

### Feature 7: Basic analytics

- Retrieve metrics actually exposed by connected platforms.
- Store time-stamped metric snapshots.
- Display basic trends.
- Distinguish missing data from zero values.
- Show the source and retrieval time of metrics.
- Produce initial recommendations grounded in collected data.

### Feature 8: Autonomy controls

- Manual mode.
- Semi-automatic mode.
- Automatic mode.
- Approval workflows.
- Action history.
- Pause and cancellation controls.
- Policy checks before external execution.

### Feature 9: Usage and operational visibility

- Track AI usage and estimated cost where measurable.
- Track external API failures.
- Record job outcomes.
- Provide actionable error states.
- Establish per-organization usage limits.

Implement basic internal usage controls before adding a complex commercial billing system.

---

## 13. Explicitly Out of Scope for the MVP

Do not implement these unless the product owner explicitly changes the scope:

- FP&A or accounting functionality.
- Bank integrations.
- Automatic financial forecasting.
- Automatic ad spend management.
- A full CRM.
- A marketing agency marketplace.
- Every social platform.
- Full feature parity across platform APIs.
- Advanced attribution modeling.
- Large-scale multi-agent autonomy.
- Microservices for each domain.
- Kubernetes-based infrastructure.
- Complex enterprise billing.
- An in-house foundation model.
- Unnecessary vector databases or knowledge graphs.
- A general-purpose workflow builder before concrete workflows are validated.

The architecture should allow future growth without implementing future complexity today.

---

## 14. Frontend User Experience

Build a coherent, professional SaaS interface rather than a collection of disconnected screens.

Initial application areas:

- Authentication.
- Organization setup.
- Business onboarding.
- Dashboard.
- Marketing strategy.
- Campaigns.
- Content studio.
- Calendar.
- Social accounts.
- Publishing history.
- Analytics.
- Recommendations.
- Automation settings.
- Organization settings.

### UI principles

- Responsive and accessible.
- Clear navigation.
- Consistent design tokens and components.
- Useful empty states for new organizations.
- Clear loading, success, and failure states.
- Clear validation messages.
- No fake charts or invented business data presented as real.
- No destructive action without appropriate confirmation.
- Clear distinctions between drafts, pending approvals, scheduled posts, and published posts.
- Clear indicators for connected, expired, or disconnected social accounts.
- Clear display of the selected autonomy mode and its consequences.

The dashboard should prioritize actionable information, not decorative metrics.

Do not build every page before the corresponding backend capability exists. Use deliberate placeholders only when clearly identified and useful for incremental development.

---

## 15. API Design

Use versioned REST APIs, beginning with a `/api/v1/` namespace.

Possible route groups:

```text
/api/v1/auth/
/api/v1/organizations/
/api/v1/business-profile/
/api/v1/brand/
/api/v1/marketing-plans/
/api/v1/campaigns/
/api/v1/content/
/api/v1/approvals/
/api/v1/social-accounts/
/api/v1/publishing/
/api/v1/analytics/
/api/v1/recommendations/
/api/v1/automation/
/api/v1/usage/
```

These are initial route groupings, not a mandate to implement every endpoint immediately.

### API requirements

- Consistent error-response structure.
- Input and output validation.
- Pagination for list endpoints.
- Appropriate filtering and sorting.
- Explicit authorization.
- Idempotency for operations with consequential external effects.
- Rate limiting where appropriate.
- OpenAPI documentation.
- Clear status codes.
- No leakage of stack traces or secrets.
- Durable handling of long-running tasks.

For long-running operations, return an appropriate operation or resource identifier and provide a status endpoint instead of holding an HTTP request open indefinitely.

Use typed frontend API functions and validate important API contracts through tests.

---

## 16. Analytics and Recommendations

Analytics must be based on actual retrieved data. Do not fabricate engagement rates, impressions, clicks, conversions, or other metrics.

For every metric, define:

- Source platform.
- Metric name.
- Value and unit.
- Measurement window.
- Retrieval time.
- Relevant account or post.
- Known limitations.

Different platforms may expose different metrics or definitions. Preserve source-specific information and avoid misleading comparisons.

Initial recommendations should be simple, explainable, and evidence-based.

For example, the system may recommend reviewing a post format when observed performance differs from an account's historical baseline. It must distinguish observed evidence from speculative explanations.

Do not claim causality merely because two measurements changed together.

As data accumulates, improve recommendations using content performance, posting consistency, campaign objectives, available audience metrics, historical performance, and stated business goals.

Recommendations should explain what was observed, why an action is suggested, and what uncertainty remains.

---

## 17. Usage, Cost, and Commercial Readiness

AI usage and external API operations can create variable operating costs. Track usage per organization where practical.

Record:

- Provider and model.
- Operation or workflow.
- Organization.
- Usage quantities when available.
- Estimated cost and currency.
- Timestamp.
- Success or failure.
- Relevant request identifiers.

Never present estimated cost as an exact invoice amount unless based on verified billing data.

Implement configurable limits for AI requests, media storage, background jobs, and other material resources where needed.

Do not build a complicated subscription system before the core product is usable. First make usage measurable and enforce basic limits; introduce commercial plans after pricing assumptions can be validated.

---

## 18. Security, Privacy, and Reliability

Security must be considered in every phase.

### Application security

- Validate all user inputs.
- Apply server-side permissions.
- Enforce tenant isolation.
- Use secure authentication and session practices.
- Protect secrets and integration credentials.
- Use HTTPS in production.
- Restrict CORS appropriately.
- Protect against CSRF when applicable.
- Apply appropriate rate limits.
- Secure file uploads.
- Prevent unauthorized access to object-storage assets.
- Avoid sensitive information in logs.
- Keep dependencies updated and scan them through the development pipeline.

### OAuth and integrations

- Validate OAuth state.
- Use PKCE when supported and appropriate.
- Validate redirect URIs.
- Store access and refresh tokens securely.
- Refresh credentials according to provider rules.
- Handle revocation and disconnection.
- Do not expose provider tokens to the browser.
- Restrict permissions to what is necessary.
- Make reauthorization states visible to users.

### Reliability

- Use timeouts for external calls.
- Classify retryable and non-retryable errors.
- Use bounded exponential backoff with jitter where appropriate.
- Prevent duplicate jobs and publications.
- Make background processing observable.
- Track job failures.
- Reconcile uncertain external outcomes.
- Use database transactions and appropriate locking for critical state changes.
- Implement health checks.
- Establish database backup and restore procedures for production.
- Document data retention and deletion.

Do not claim production security merely because authentication works. Document what has actually been tested and what remains to be reviewed.

---

## 19. Testing Strategy

Testing is required throughout development, not postponed until launch.

### Backend tests

- Unit tests for domain services.
- API tests.
- Authentication and authorization tests.
- Tenant-isolation tests.
- Database constraint tests.
- AI provider adapter tests.
- AI output validation tests.
- Publishing state-transition tests.
- Automation policy tests.
- Retry and idempotency tests.
- Token expiration and reconnection tests.

### Frontend tests

- Component tests for important interactions.
- Form validation tests.
- API error-state tests.
- Authentication and organization-switching tests.
- Approval and publishing workflow tests.
- Accessibility checks for key flows.

### Integration and end-to-end tests

Test the complete flow:

1. Create an account.
2. Create an organization.
3. Complete business onboarding.
4. Generate a marketing plan.
5. Create and edit content.
6. Submit content for approval.
7. Approve content.
8. Submit a publishing job.
9. Verify the resulting status.
10. Retrieve metrics when supported.
11. Generate an evidence-based recommendation.
12. Verify the workflow respects each autonomy mode.

Use mock social adapters for deterministic automated tests. Use real platform integrations in a controlled environment when credentials and permissions are available.

Never mark a real external integration test as successful when only a mock was exercised.

---

## 20. Development and Deployment Environment

Provide a reproducible local development environment.

The root Docker Compose configuration should support necessary services, such as:

- PostgreSQL.
- Redis.
- Backend API.
- Celery worker.
- Scheduler, if needed.
- Frontend.

Do not require every service to run inside Docker if a simpler local setup improves development. Document the supported setup clearly.

Provide:

- `.env.example` with safe placeholders.
- Database migration instructions.
- Test commands.
- Lint and formatting commands.
- Frontend development commands.
- Backend development commands.
- Worker startup instructions.
- A clean setup guide.
- Troubleshooting notes.
- Production deployment guidance.

Never commit real API keys, passwords, OAuth secrets, or production environment files.

Use separate development and production settings. Do not rely on development defaults for production security.

---

## 21. Implementation Roadmap

Each phase must produce a usable and verifiable result.

### Phase 0 — Repository and architecture foundation

**Objectives**

- Create the repository.
- Create `frontend/`, `backend/`, `infrastructure/`, and `docs/`.
- Initialize Next.js and Django.
- Establish Python and Node dependency management.
- Add Docker Compose for local dependencies.
- Configure linting, formatting, type checking, and tests.
- Add environment templates.
- Add a health endpoint.
- Add architecture documentation.
- Verify frontend and backend run independently.

**Deliverables**

- Runnable frontend.
- Runnable backend.
- Reproducible local setup.
- Basic CI.
- Initial architecture decision records.

Do not begin complex business functionality before this foundation works.

### Phase 1 — Authentication and multi-tenancy

Implement:

- User authentication.
- Organization creation.
- Organization memberships.
- Role-based permissions.
- Organization-scoped API patterns.
- Audit-event foundation.
- Frontend authentication and organization context.

Tests must demonstrate that one organization cannot access another organization's data.

### Phase 2 — Business onboarding and brand context

Implement:

- Business profile.
- Industry presets.
- Audience and goals.
- Brand voice and guidelines.
- Asset metadata and upload flow.
- Editable business context.
- Onboarding progress and validation.

Verify that separate organizations maintain independent business and brand contexts.

### Phase 3 — AI provider abstraction

Implement:

- Provider interface.
- One configured provider.
- Configuration and secrets management.
- Structured-output validation.
- Error handling and timeouts.
- Usage tracking.
- Basic cost estimation.
- Mock provider for automated tests.

Document how a second provider would be added without changing marketing business logic.

### Phase 4 — Marketing strategy

Implement:

- Marketing plan generation.
- Objectives.
- Content themes.
- Campaign concepts.
- Suggested metrics.
- Strategy history and editing.
- Organization-specific context assembly.

Verify output quality with representative test cases from multiple industries.

### Phase 5 — Content studio

Implement:

- Content generation.
- Platform-specific content variants.
- Editing and version history.
- Content assets and briefs.
- Brand-guideline checks.
- Content statuses.
- Clear UI for regeneration and review.

Do not require image generation to complete this phase.

### Phase 6 — Campaigns, calendar, and approvals

Implement:

- Campaign CRUD.
- Content-to-campaign relationships.
- Calendar.
- Approval requests.
- Approve and reject actions.
- Revision workflows.
- Audit history.

Verify that only authorized users can approve and publish content.

### Phase 7 — Social integration foundation and first real platform

Implement:

- Shared integration contract.
- Mock social adapter.
- Account connection model.
- Credential lifecycle.
- Capability metadata.
- Publishing-job lifecycle.
- Retry and duplicate-prevention mechanisms.

Inspect current official documentation for Instagram, TikTok, and Facebook before choosing the first production integration.

Choose the first real integration based on validated API access and publishing requirements. Demonstrate a real account-connection and publication workflow in an authorized test environment. Document remaining app-review or production-access limitations.

### Phase 8 — Remaining social platforms

Add the other two integrations incrementally.

Reuse the shared contract while implementing platform-specific behavior where necessary.

Validate each platform's account eligibility, content formats, publication flow, token lifecycle, and analytics availability.

Do not falsely claim complete platform parity.

### Phase 9 — Analytics and recommendations

Implement:

- Metric definitions and snapshots.
- Platform-specific metric retrieval.
- Basic performance dashboards.
- Historical comparisons where data supports them.
- Evidence-backed recommendations.
- Clear handling of unavailable or incomplete metrics.

Verify that the UI never confuses missing metrics with zero.

### Phase 10 — Autonomy and policy engine

Implement:

- Manual, semi-automatic, and automatic modes.
- Organization-level settings.
- Workflow-level policies where useful.
- Approval gates.
- Durable action records.
- Idempotent execution.
- Retry and cancellation behavior.
- Pause controls.
- Audit history.
- Policy-change handling.

Test that automatic mode cannot bypass authorization, approval requirements, platform capabilities, or other applicable limits.

### Phase 11 — Usage controls and operational hardening

Implement:

- Usage tracking.
- Basic quotas.
- Structured logs.
- Health checks.
- Job monitoring.
- Error visibility.
- Backup and restore documentation.
- Production configuration.
- Security review.
- Deployment documentation.
- CI verification.

Introduce billing only when the core workflow and initial customer requirements justify it.

### Phase 12 — Pilot and launch readiness

Prepare a controlled customer pilot.

Validate:

- Onboarding completion.
- AI output quality.
- Content editing and approval.
- Real social publishing.
- Failure recovery.
- Autonomy controls.
- Analytics accuracy.
- Tenant isolation.
- Usage costs.
- User feedback.

Document known limitations and prioritize improvements based on real customer usage.

Do not declare the product ready merely because all pages exist or the build passes.

---

## 22. Definition of Done

A feature is not complete simply because code has been written.

For every meaningful feature:

1. Its scope and behavior are understood.
2. Domain logic is implemented in the appropriate module.
3. The API contract is documented where applicable.
4. Authorization and tenant isolation are enforced.
5. Validation and failure handling are implemented.
6. Automated tests cover important behavior.
7. The frontend handles loading, success, and error states where applicable.
8. Database migrations are included where needed.
9. Relevant logs and audit events exist.
10. Documentation is updated.
11. Relevant tests and checks have actually been run.
12. Remaining limitations are explicitly reported.

For external integrations, distinguish between:

- Code implemented.
- Mock tests passed.
- Real credentials configured.
- Real external flow tested.
- Production access or provider review completed.

These are different milestones and must be reported separately.

---

## 23. Coding-Agent Workflow

### Before each phase

- Review the current repository state.
- Review relevant architecture decisions.
- Identify the smallest useful implementation slice.
- Identify security and external dependencies.
- Define acceptance criteria.
- Explain any material decision that changes scope or architecture.

### During implementation

- Work in small, coherent changes.
- Keep code organized by responsibility.
- Prefer clear and maintainable solutions over clever abstractions.
- Add tests alongside implementation.
- Run relevant checks before proceeding.
- Avoid unrelated refactoring.
- Do not introduce dependencies without a reason.
- Never silently replace a real integration with a mock.
- Never expose secrets in output or logs.

### After each phase

Provide a concise report containing:

1. **Implemented:** what is actually complete.
2. **Files and modules:** important locations changed.
3. **Verification:** commands run and their actual results.
4. **Limitations:** what is incomplete, mocked, blocked, or unverified.
5. **Architecture decisions:** meaningful changes and their rationale.
6. **Next phase:** the recommended next implementation slice.

Do not state that a test passed if it was not executed.

Do not claim to have deployed, connected an account, published a post, or verified provider access unless the action actually occurred.

### Decision boundaries

Make ordinary implementation decisions independently when they are reversible and consistent with this specification.

Ask the product owner before making a significant decision that changes:

- The overall technology stack.
- The multi-tenant security model.
- The product's initial scope.
- External financial commitments.
- Data handling or privacy assumptions.
- Irreversible migrations.
- A major third-party dependency.
- Agreed autonomy and approval boundaries.

When external information is required, consult current authoritative documentation rather than relying on assumptions.

---

## 24. First Task: Begin Implementation

Start with **Phase 0**. Do not respond with another generic product plan. Begin the actual repository work.

First actions:

1. Inspect the available working directory and development environment.
2. Confirm whether the target directory is empty and whether any files must be preserved.
3. Create the project structure with separate top-level `frontend/` and `backend/` directories.
4. Initialize the frontend and backend independently.
5. Establish compatible dependency versions and development commands.
6. Configure PostgreSQL and Redis for local development.
7. Create a minimal health endpoint in Django.
8. Create a minimal frontend page that can communicate with the backend.
9. Add a small initial test suite and CI checks.
10. Write setup instructions and initial architecture decisions.
11. Run the application and relevant tests.
12. Report actual results and propose the next small implementation slice.

Do not implement all marketing features in the first pass. Establish a clean, working foundation, verify it, and proceed phase by phase.

If the environment cannot create files or run commands directly, provide the exact commands and files needed for the next executable step, clearly stating what has and has not been executed.

The goal is to build a reliable, extensible AI Marketing Cloud that can acquire real customers—not merely a technically impressive prototype.
"""
