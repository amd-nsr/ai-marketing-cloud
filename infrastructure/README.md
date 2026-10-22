# Infrastructure

Deployment and infrastructure configuration, kept separate from application code.

Currently empty by design. Dockerfiles live with their apps (`backend/Dockerfile`,
`frontend/Dockerfile`, see ADR 0001); the local stack is the root `docker-compose.yml`.
Hosting-specific configuration (deployment manifests, IaC, backup scripts) is added here
once a hosting platform is chosen (Phase 11).
