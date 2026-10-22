# 0004 — Custom User model from the first migration

**Status:** Accepted (2026-10-19)

## Context
Django strongly recommends defining a custom user model before the first migration;
changing `AUTH_USER_MODEL` afterwards requires a painful manual data migration.

## Decision
`apps.accounts.User` (`AbstractBaseUser` + `PermissionsMixin`):
- UUID primary key (consistent identifier strategy; not enumerable).
- Email is the login identifier; stored lowercase and unique **case-insensitively** via
  a `Lower(email)` database constraint (in addition to `unique=True`, which Django
  requires for `USERNAME_FIELD`).
- No username. `full_name` only; richer profile data belongs elsewhere.
- Users are global; organization membership and roles are separate models (Phase 1).
  A user may belong to many organizations.

## Consequences
- Login, admin, and `createsuperuser` work by email.
- All future tenant-scoped models reference `settings.AUTH_USER_MODEL` and an
  organization; users themselves are not tenant-scoped.
