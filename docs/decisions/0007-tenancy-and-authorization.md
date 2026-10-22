# 0007 — Tenancy and authorization pattern

**Status:** Accepted (2026-10-19)

## Context
Tenant isolation must hold for every endpoint added in later phases, written by
different people at different times. The pattern must make the safe path the easy path.

## Decision
- **Organization in the URL:** every tenant-scoped endpoint is nested under
  `/api/v1/orgs/<org_id>/...`. No implicit "current organization" in the session.
  The frontend mirrors this with `/o/<orgId>/...` routes, which also makes organization
  switching a navigation, not hidden state.
- **One base class:** `OrganizationScopedMixin` / `OrganizationScopedViewSet`
  (`apps/organizations/api.py`) resolves the caller's `Membership` for the URL's
  organization on every request, returns **404** for non-members, checks a declared
  permission (`read_permission`, `write_permission`, `action_permissions`), and filters
  querysets with `organization=self.organization`. Creates always set the organization
  server-side; client-supplied organization IDs in bodies are never trusted.
- **Related objects:** serializers reference other tenant objects only through
  `OrgScopedRelatedField`, which restricts the lookup to the same organization.
- **Data model:** every tenant-scoped model inherits `OrganizationOwnedModel`
  (UUID pk, `organization` FK, timestamps).
- **Roles:** a fixed role → permission matrix in code (`roles.py`, documented in
  `docs/security/roles.md`). Custom roles are out of scope for the MVP.
- **Auth:** Django session authentication through the same-origin proxy (ADR 0003);
  CSRF enforced, including on anonymous login/register/reset endpoints (login CSRF).
  Credential endpoints are rate-limited per client IP (`NUM_PROXIES` must match the
  number of trusted proxies in front of Django).
- **Audit:** `apps.audit.services.record()` for security- and business-relevant actions;
  metadata is scrubbed of secret-looking keys.

## Consequences
- Every new domain endpoint gets tenant isolation by inheriting one class; tests in
  `tests/test_tenant_isolation.py` show the pattern. Each new domain adds its own
  isolation tests (cross-org read, write, and object-ID substitution).
- Organization-level signals (`organization_created`) let later apps create defaults
  (automation policy, quotas) without the organizations app importing them.
- No email verification yet: registration trusts the address until invitations or
  password reset prove it. Revisit before public launch (see security baseline).
