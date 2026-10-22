# 0012 — Autonomy modes and the automation policy engine

**Status:** Accepted (2026-10-20)

## Decision
- **One engine, three modes** (`apps/automation/policy.py`). Manual, semi-automatic and
  automatic are settings of one policy evaluated before every automated action; there are
  no separate code paths per mode. Default for every organization: **manual**.
- **Evaluation order** (the brief's ten checks): initiator → permissions → mode/pause →
  workflow authorization (auto-publish switch, allowed accounts) → content approval →
  content/brand rules → platform capabilities → window and automated-post cap → usage
  limits → current state. Outcomes: `execute`, `await_approval`, `reject`, `defer`,
  `cancel`, always with human-readable reasons.
- **What each mode allows the system to do on its own:**
  - manual: nothing;
  - semi-automatic: propose; every publication waits for a person with
    `automation.approve`;
  - automatic: publish content a person already approved, only to allowed accounts,
    within the weekday/hour window, under the daily automated-post cap, with the
    auto-publish switch on. Anything outside that becomes `await_approval`.
  A person's approval of an action never overrides hard checks (content approval, brand
  rules, platform capabilities, usage limits, state). Other action types (ad budgets,
  spending, connecting accounts) are always rejected for automation.
- **People keep control in every mode**: users with `publishing.publish` can publish and
  schedule approved content themselves.
- **Durable actions** (`AutomationAction`): type, workflow, resource, decision, reasons,
  policy version and mode at decision, approver, attempts, error, resulting publishing
  job / AI run. Idempotency key per proposal (`publish:<item>:<account>:v<version>`);
  only `approved` actions execute (row-locked). The publishing engine independently
  refuses automation-initiated jobs without a cleared action.
- **Policy changes and pause**: every change bumps the policy version and re-evaluates
  pending actions. Unsent automated posts are re-checked; those no longer allowed are
  cancelled and (unless now manual) re-proposed for approval. Rejected actions are never
  revived. Pause holds automated scheduled posts and defers actions; "cancel all pending"
  cancels every waiting action and unsent automated post.
- **Workflows**: calendar auto-publish (approved content with `planned_for` in the next
  48h) and plan drafting (drafts for the active plan's calendar, capped per week; drafts
  always need approval). Beat runs them every 15 minutes; deferred actions are
  reconsidered every 5 minutes.

## Consequences
- Automation can only act on content a person approved; there is no auto-approval of AI
  content in the MVP.
- Workflow-level policies beyond the organization policy are not implemented yet.
