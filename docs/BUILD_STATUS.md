Build status

Current stage: M0–M3 complete in preview mode. M4 and later stages are not implemented.

Hosting preparation update: the hosted-preview part of M4 is in progress; live email and paid AI remain disabled. Added a production settings module, Gunicorn/WhiteNoise, a non-root Docker image definition, Render web/worker/managed-database blueprint, and docs/HOSTED_PREVIEW.md. No cloud service has been created, no hosting charge incurred, and no hosted URL exists yet.

Hosting validation: 65 tests passed (the existing 62 plus HTTPS redirect, secure CSRF cookie, and disallowed-host checks); Ruff lint and format checks passed. Production `check --deploy --fail-level WARNING` passed with two documented provider-domain HSTS checks intentionally silenced. Production collectstatic and the actual Gunicorn startup script passed: health, protected home, login, hashed CSS and no-store headers verified. The first test run exposed a static-manifest requirement leaking into development; manifest storage was moved into production settings and all 65 tests then passed. Docker builds failed at package installation due to build-container DNS, including a host-network retry; the complete image is unverified. Render documentation/pricing access returned proxy HTTP 403. Render account access, current plan validation/quote, remote build/deployment, real account provisioning, and backup/restore verification remain outstanding.

| Milestone | State | Evidence / next action |
| --- | --- | --- |
| M0 Foundation | Passed | Django 5.2.17 on Python 3.12.14, locked dependencies, PostgreSQL 16 Docker service, migrations, invite-only custom email-login model, synthetic demo guard. |
| M1 Access and planning | Passed | Household membership, single-use expiring invitations, shared/private plans and routines, bounded source notes, exports, trips, separate departure/arrival zones, explicit unknown times. |
| M2 Briefing and worker | Passed | Shared and separate private previews, prior-evening preparation, confirmed trip buffers, local-time/DST schedules, durable leased jobs, per-recipient delivery, deduplication, privacy revalidation, catch-up limits, pause controls. |
| M3 Approvals and budgets | Passed | All-in USD policy, exact authenticated approvals, stale quote/revision checks, ownership restrictions, simulated actions, ambiguous outcomes, unknown subscription costs, atomic usage reservations and reconciliation. |
| M4 Email and deployed pilot | Not started | Configure actual costs, an authorized sender, verified recipients, and hosting. Implement and verify a live adapter separately. |
| M5 Model gateway and roles | Not started | No model SDK, keys, paid calls, or AI-generated output exist in this release. |
| M6 Read-only integrations | Not started | No inbox, work-calendar, messaging, or fitness account access is connected. |
| M7 Specialist workflows | Not started | Add specialized home, pet, health, social, and financial workflows incrementally. |
| M8 Supported external actions | Not started | Fake connectors only; no purchases, appointments, provider messages, or bookings have been executed. |

Validation performed against PostgreSQL, with system Chromium for the mobile test:

- uv sync --locked: passed.
- python manage.py check: passed, zero issues.
- python manage.py migrate --check: passed.
- python manage.py makemigrations --check --dry-run: passed, no changes detected.
- python manage.py test: 62 tests executed and passed; no skipped tests in this run.
- ruff check and ruff format --check: passed.
- sh scripts/setup_preview.sh: exercised against the existing configuration/database; repeatable without overwriting credentials.
- scripts/start_preview.py: exercised twice, reused only this checkout's processes; health and login HTTP responses validated.
- scripts/stop_preview.py followed by start: exercised successfully.
- run_worker --once: command exercised in preview mode. The empty application database initially has no household; nonzero scheduling/delivery behavior is validated by the PostgreSQL tests and browser flow.

The browser test covers real email/password login, mobile plan creation, shared/private briefing isolation, exact approval, and a simulated completion. It also checks the narrow layout for horizontal overflow. Its fictional-data screenshot is at /tmp/workforce-mobile-preview.png.

Concurrency tests use separate PostgreSQL connections: two worker claimers start one job, and two usage reservations cannot oversubscribe one allowance. Failure tests cover expired leases after submission, unknown external outcomes, bounded retries, source deletion, changed privacy after queueing, quote changes, revoked approvers, CSRF, and cross-household IDs. Tests use fictional accounts and no live paid APIs.

Current runtime: local preview web process and worker are running, backed by Docker PostgreSQL. The development server is not a deployed household service. Local credentials, logs, and process IDs are in ignored files; the private household interview remains outside this public checkout. The initial readme.md is unchanged.

A real household account has not been provisioned. bootstrap_household provides private password entry, and the application provides partner invitations. Demo accounts have unusable passwords unless explicitly changed for local review. Preview password-reset messages stay in process memory and are not delivered.

Exact next task: perform M4 account/cost discovery, select a supported sender and hosting setup, and implement a separately verified live delivery adapter and production operation. Keep the current tests and preview path. Existing subscriptions and actual household preferences are recorded privately; do not copy them into source control.
