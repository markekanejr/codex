Personal workforce — coding plan and acceptance contract

Status: M0–M3 implemented and verified; see docs/BUILD_STATUS.md. This contract describes both completed and future milestones. The current application uses preview transports only; live account integrations, paid model calls, and deployment belong to later milestones.

This is a generic engineering document suitable for this public repository. Actual household names, addresses, routines, providers, trips, health goals, financial records, recipient addresses, and credentials belong in private configuration. The private interview brief currently lives outside this checkout at /workspace/personal-workforce-design.md. Read it when available, but never copy it into source control, fixtures, screenshots, logs, issue descriptions, or a pull request.

The intended product is a mobile-friendly personal assistant for a small household. It coordinates travel, appointments, household tasks, health habits, relationships, and budgeting. Eight logical roles share one application, database, scheduler, policy engine, and cost budget. The owner and partner use ordinary language and existing apps. The application must deliver value before every integration is available.

The first release allows two invited people to record plans, distinguish shared and private information, enter a confirmed itinerary, preview a morning briefing, receive approved email delivery, and review action proposals. It must work using deterministic logic and manual inputs. Model calls and account integrations improve that working foundation.

Decisions already made:

| Area | Implementation decision |
| --- | --- |
| Application | Python 3.12 and Django 5.2 LTS, one Django application named workforce |
| Database | PostgreSQL 16; use it for development and concurrency tests as well as production |
| Frontend | Django templates, responsive CSS, minimal JavaScript and progressive enhancement |
| Authentication | Django sessions, CSRF protection, password reset, and invite-only household membership |
| Dependencies | uv with pyproject.toml and a committed uv.lock; frozen/locked installs after resolution |
| Background work | A Django management command polling durable PostgreSQL jobs; short transactions and leases |
| AI | One provider gateway, initially OpenAI if a suitable account is available; model ID configurable |
| Email | A transport interface with an in-app preview/fake transport first; choose the live adapter after checking available sender accounts |
| Hosting proposal | One container image deployed as a web service and worker, plus managed PostgreSQL; Render is the first platform to evaluate |
| Initial integrations | Manual personal records, then outbound email, then a narrow read-only source |
| Source control | Generic code and synthetic fixtures only; personal data stays in private storage |

Do not add a separate frontend service, Redis, Celery, a vector database, Kubernetes, or a multi-agent orchestration framework to the initial build. There is no demonstrated need for them. Add dependencies only in the milestone that needs them.

The inspected repository contains only readme.md and is clean before these planning documents. Python 3.12.14 and uv are available in the current environment. Docker's executable exists; its daemon and PostgreSQL availability have not been verified. Use the existing checkout at /workspace/codex. Cloud tasks are already isolated; do not create a Git worktree unless the user asks.

The proposed layout is:

    manage.py
    pyproject.toml
    uv.lock
    .env.example
    .gitignore
    compose.yaml
    Dockerfile
    config/
        settings.py
        urls.py
        wsgi.py
    workforce/
        models/
        services/
            access.py
            plans.py
            scheduling.py
            briefings.py
            actions.py
            spending.py
            jobs.py
            ai.py
        connectors/
            base.py
            fake.py
            email.py
        roles/
        forms/
        views/
        templates/workforce/
        static/workforce/
        management/commands/
            bootstrap_household.py
            invite_member.py
            run_worker.py
        tests/
    docs/
        IMPLEMENTATION_PLAN.md
        MODEL_HANDOFF.md
        BUILD_STATUS.md
        OPERATIONS.md

Create directories and modules as they are needed. Small related models may initially share a file. Do not manufacture empty implementations for every planned role.

The initial pages are Today, Plans, Trips, Review, and Settings. Today shows confirmed commitments, upcoming preparation, and decisions. Plans manages shared/private items and routines. Trips keeps an itinerary and its missing details together. Review shows the exact proposal, price, recipient, and changes before an approval. Settings contains household membership, connections, notification preferences, budget, and pause controls. Make forms usable on an iPhone with clear touch targets and semantic labels. Backend errors must appear as actionable messages. Implementation details belong in Settings or operational logs.

Data and access rules:

| Model/group | Essential fields and constraints |
| --- | --- |
| User, Household, Membership | Use a custom User from the first migration; unique login email. Membership defines household role, pricing-approver capability, notification preferences, and timezone. Membership does not grant access to another member's private records. |
| Invitation | Intended email, household, role, hashed single-use token, expiry, and accepted timestamp. No open public registration. |
| PlanItem | Household, owner, audience, kind, title, status, optional start/end/due timestamps, IANA timezone, revision, and optional source. Audience is shared or private; private items require an owner. |
| Routine | Household, audience, owner, local time, timezone, daily/weekly rule, weekdays, activation dates, and revision. Limit the initial recurrence editor to daily and weekly rules. |
| SourceRecord | Household, owner/audience, connector, stable external ID, observed time, source update time, provenance, and necessary extracted fields. Track user-reported versus confirmed data. Retain raw source text only when needed and protect it with the same access rules. |
| Trip and TripSegment | Household, owner/audience, status; segment type, origin/destination, departure/arrival timezone and time, source references, verification state. Unknown fields remain null. Represent flights and stays without requiring every detail at creation. |
| ActionProposal and Approval | Immutable versioned intent, affected people, proposed vendor/recipient, exact payload hash, all-in amount in integer minor units, currency, quote expiry, policy decision, approving actor, and status. A decision references a particular proposal revision. |
| ScheduledJob | Type, due_at UTC, occurrence key, related record and revision, status, lease owner/until, attempts, next retry, and minimal error classification. Unique keys prevent duplicate local occurrences. |
| Delivery | Audience principal, one recipient ID derived by code, content snapshot, constituent source IDs/revisions, occurrence/action key, provider reference, attempt state, and outcome. Unique by occurrence, recipient, and channel. Serve as the transactional outbox; avoid a second redundant outbox table. |
| Connection | Household and authorized owner, connector type, allowed capabilities, authentication status, last successful operation, sync cursor, expiry, and encrypted token material if required. |
| BudgetConfig, UsageReservation, UsageEvent | Billing month, existing subscriptions with known/unknown costs, fixed commitments, variable caps, estimated reservations, and reconciled usage. Currency is explicit. |
| AuditEvent | Actor, household, affected object, audience, state transition, timestamp, and limited diagnostic metadata. Exclude message bodies, tokens, health data, and financial exports from operational logs. |

Introduce the model groups incrementally. Do not create unused tables simply to complete this list.

All record access must pass through centralized household and audience scoping. Use the same access service for detail views, lists, edits, search, exports, background jobs, linked records, notification history, and model inputs. A private item cannot become visible by linking it to a shared trip. Deleting or hiding a source must invalidate dependent cached output as appropriate.

Build shared briefings from shared-only queries before calling an LLM. Private briefings use a separate recipient-scoped query and separate model request. Never send mixed private data to a model and ask it to redact afterward. An optional busy block for a private appointment is an explicitly shared derivative with only the permitted timing and generic label.

Worker credentials and application-level administrative access do not relax these audience rules. Do not expose personal domain tables through unrestricted Django admin screens. The household pricing approver is not automatically entitled to the partner's private information. If a private action needs that person's financial approval, require an intentionally shared approval summary containing the information needed for the decision. Otherwise leave the transaction manual; never silently expose the underlying private records.

Actions use this lifecycle:

    draft -> needs_information | awaiting_approval | ready
    awaiting_approval -> ready | rejected | expired
    ready -> queued -> executing
    executing -> succeeded | failed | outcome_unknown
    draft/ready/queued -> canceled when permitted

Record how an action became ready: explicit human approval or an applicable routine policy. Execution checks the current record revision, approval, capabilities, pause settings, quote expiry, and affected-person constraints again.

The policy service returns a structured result such as allowed, approval_required, information_required, or unsupported, with reasons. It receives structured facts, not an LLM's permission judgment. Store money as integer cents for USD; unsupported currencies require an explicit decision until conversion rules exist.

The actual auto-spend threshold and approver come from private configuration. Boundary tests may use a fictional household configured with a 10,000-cent limit: 10,000 cents can be eligible; 10,001 cents or 9,500 cents plus 800 cents in fees require approval. Eligibility also requires an enabled routine workflow, permitted vendor/recipient, complete quote, and appropriate availability. Do not split one purchase into multiple proposals to bypass the limit. New recurring commitments and unknown totals require an explicit decision.

An approval binds vendor, recipient, full price/currency, dates, material terms, and proposal revision. Changed terms or prices invalidate it. Authenticated, CSRF-protected POST requests approve or reject actions. Email links only open the application; GET requests never approve, send, or purchase.

If an external request times out after submission, its outcome may be unknown. Reconcile against the provider's receipt or idempotency support before retrying. An HTTP success from a model or a queued job is not a provider booking confirmation. Initially, use a fake booking connector to validate this lifecycle; enable actual external writes one supported workflow at a time.

Scheduling and delivery rules:

- Store instants in UTC and recurrence rules in IANA local timezones. Generate each next local occurrence; never add a fixed 24 hours to implement a daily local schedule.
- Use one logical occurrence key per household, visibility principal, briefing type, and local date. The principal is the household for a shared briefing and the owner/recipient user ID for a private briefing. Both members' private briefings and the shared briefing must coexist on the same date. Edits revise or retire work for the same occurrence rather than creating duplicate messages.
- Claim due jobs using PostgreSQL row locking and short transactions, including skip-locked behavior. Release locks before external I/O. Use leases and heartbeats for recovery. If a lease expires after external submission may have begun, recover into outcome-unknown/reconciliation, never automatically resubmit.
- Revalidate the source revision before executing a claimed job. A changed or canceled flight retires obsolete departure reminders. Before sending a stored content snapshot, revalidate every constituent record's visibility and revision; rebuild or cancel if it became private, changed, or was deleted.
- Define a configurable catch-up window. Start with 90 minutes for a missed morning briefing; skip and record older morning occurrences. Event-specific reminders have their own expiry and usefulness rules.
- Send shared and private messages through separate jobs. Shared content can be assembled once, but create a Delivery row and idempotency key per actual recipient/channel so partial success is recoverable without resending to everyone. Application code resolves recipients from verified household memberships; imported text and model output cannot supply arbitrary recipients.
- Use provider idempotency where available, but do not claim exactly-once delivery. Ambiguous outcomes must be visible and reconciled instead of blindly retried.
- Support a household pause for all external actions and a separate pause for paid AI use. Ordinary deterministic features continue within available, already-budgeted service capacity.
- For daylight-saving gaps, choose the next valid local time; for a repeated time, use the first occurrence once. Cover these policies with tests. The default morning time is not itself in the DST transition hour.

AI contract:

The gateway exposes typed operations such as extract_trip, propose_schedule, summarize_progress, and suggest_activities. Use the provider SDK only inside the gateway. Roles return schema-validated proposals with source references and missing fields. They do not directly send email, alter permissions, spend money, or mutate calendars.

Start with one configurable model and one provider, plus a deterministic fake. Add a more capable fallback only when evaluation shows a need. Do not hard-code an unverified current model name or price. Set deadlines, output limits, bounded retries, and cost reservations. Keep chat subscriptions distinct from API billing.

Imported email, web content, calendar descriptions, and attachments are untrusted data. Extract narrowly and validate types, dates, durations, currencies, and source references. Do not follow instructions embedded in a confirmation email. Resolve IDs, recipients, and authorization in application code. No generic shell, arbitrary URL-fetch, or unrestricted messaging tool belongs in the model's toolset.

Cost control must reserve estimated cost atomically before concurrent model calls. Count known subscription and hosting commitments before allocating variable usage. Unknown subscription costs remain unknown rather than zero. Reconcile reservations against returned usage or a conservative upper bound when actual usage is missing. Verify current provider pricing before enabling unattended paid execution, and also configure provider-side limits when available.

Eight role modules share these services:

| Role | First concrete capability | Data dependency |
| --- | --- | --- |
| Chief of staff | Assemble briefing and rank pending decisions | Plans, tasks, approvals, visibility, and schedule |
| Travel | Build verified itinerary and preparation checklist | User-confirmed trip or selected confirmation |
| Home/life administrator | Maintain recurring upkeep, appointment, and pet-care tasks | Explicit provider/contact records and due dates |
| Health/fitness | Schedule activity opportunities and summarize supplied trends | Existing-app summaries or supported exports |
| Relationships/community | Suggest social opportunities, birthday reminders, and gifts | Explicit preferences, contact dates, and availability |
| Finance | Create annual/monthly budget scenarios and identify irregular expenses | User-provided household figures or redacted CSV |
| Reliability | Detect stale sources, conflicts, failed jobs, and missing access | Operational state; mostly deterministic code |
| Creative adviser | Offer occasional context-appropriate ideas | Approved interests, budget, and available time |

Use suggested activities with labeled evidence. Never fabricate restaurant availability, live flight status, a completed sync, or a confirmed booking. Specialist suggestions become ordinary proposals in the same Review flow.

Integration order and boundaries:

1. Manual forms and pasted plain-text personal records. Begin with bounded text/CSV inputs and synthetic examples; add attachment parsing only when needed.
2. Outbound email using a sender the household has explicitly configured. Inspect available account/connector capabilities before asking for a new service. The user has accepted email as the initial channel.
3. Calendar invitations as an additive bridge to existing calendars. Use a maintained iCalendar library, stable UID, increasing SEQUENCE, correct timezone information, and explicit cancellation/update behavior. An invitation is not proof of acceptance or availability.
4. One selected personal email or calendar source. Prefer deliberate forwarding or selected personal records. Work-managed Outlook access must respect the personal-life scope; availability and selected personal content are the only intended inputs.
5. Health summaries and authorized household communications. Verify actual exports/APIs before choosing adapters.
6. Group messaging only after proving the intended group can receive automated messages through a supported service.

The live email vendor is the main deliberate provider decision left open. A verified existing SMTP or supported OAuth sender may avoid another subscription. A transactional service may require a domain the user does not have. Do not buy a domain or assume unattended Gmail access; check the actual options when reaching live delivery. The transport interface allows all earlier work to proceed.

For Microsoft, verify tenant consent and scopes. An event being personal does not mean OAuth access can be limited to that event. ICS subscriptions can be a useful calendar view but refresh asynchronously, so they cannot establish live availability or schedule time-critical reminders.

For retained fitness apps, keep logging in the existing tools. Use only supported APIs, exports, or user-supplied summaries. Verify what a stored weight field represents and when it was updated; a wearable connection is not proof of new body-weight readings. Do not create fake synchronization buttons.

Connection health is evidence-based: configured, authenticated, available capabilities, last successful operation, last attempt, and error state. Use a read-only capability probe before marking a connection usable. Handle token revocation, pagination, incremental cursors, deletions, and stale data. Keep encrypted refresh tokens server-side; no credentials in templates, browser storage, logs, or fixtures.

Implementation milestones follow. Complete each acceptance gate and update docs/BUILD_STATUS.md before moving on. A missing external account blocks only the dependent live capability; continue independent implementation and testing.

M0: Build the project foundation.

Create the Django project, custom user model, dependency lock, development PostgreSQL configuration, environment example, and ignore rules. Start with Django, psycopg, and the necessary configuration helpers; add deployment and model packages later. Use localhost-only development defaults. Ignore .venv, .env files, databases, uploads, exported data, caches, and private configuration.

Create a synthetic demo loader with fictional people and events. It must refuse production settings. Live outbound delivery and paid AI are disabled by default. Do not hard-code real passwords or automatically create users on every startup.

Acceptance: uv sync --locked succeeds; migrations apply to PostgreSQL; Django system checks pass; the root/login page works; the demo loader cannot activate in production; .env.example contains names and harmless placeholders only.

M1: Implement membership, audience isolation, and planning forms.

Implement invitations, login/logout/password reset, PlanItem, Routine, SourceRecord, basic Trip/TripSegment, and the centralized access service. Provide shared/private labels, useful missing-information states, and mobile-friendly form errors. User-reported trip facts can be saved without inventing missing times.

Acceptance: two members can use shared records; each sees only their own private records; a third household cannot retrieve either household's data even by guessing object IDs. Test list/detail/update/export and linked-record routes. Unknown itinerary fields survive round trips through forms and database storage.

M2: Deliver the deterministic briefing and durable worker in preview mode.

Implement briefing construction, recipient-specific previews, local-time recurrence, job leases, Delivery outbox, fake transport, message history, and pause controls. Add a run_worker command with a one-pass mode for tests and a polling mode for a service. Derive travel preparation only from sufficient confirmed inputs and a configured arrival/transport buffer.

Acceptance: shared and private previews are correct; one shared briefing and each member's private briefing coexist per local date, with one delivery per actual recipient/channel; two workers do not begin the same delivery; expired leases recover safely; canceled/edited events invalidate old work; a record made private after queueing cannot leak through an old snapshot; stale briefings are skipped after downtime. All this works with no model key.

M3: Implement approvals and budget controls.

Build ActionProposal, Approval, policy evaluation, the Review page, fake external actions, cost configuration, UsageReservation, and UsageEvent. Implement idempotent form submissions, stale-approval detection, and outcome-unknown handling. Put complete transaction information in approval requests.

Acceptance: money boundaries, changed quotes, unauthorized approvers, repeat clicks, CSRF/GET behavior, household ownership, and concurrent cost reservations are covered. Unknown fixed subscription costs remain visibly incomplete and prevent an unverified claim that unattended paid use fits the budget.

M0 through M3 form the first fully local deliverable. A working briefing preview, itinerary, approvals demonstration, and all associated tests should be reviewable before requesting any live account configuration.

M4: Activate email and deploy the first pilot.

Check current subscriptions and available sender/hosting accounts. Produce a concrete hosting/email choice and cost estimate. Add the selected email adapter and verify sender identity, recipient addresses, supported retry behavior, and authentication. Test delivery only to explicitly authorized household recipients. Record provider acceptance separately from inbox receipt.

Build the deployment image, production settings, health/readiness checks, worker startup, migration command, redacted logs, backup schedule, and restore instructions. Deploy web and worker from the same image; run migrations once per release rather than independently in both processes. Keep all configuration outside source control.

Acceptance: HTTPS login works, a real sample reaches the verified recipients, a scheduled delivery survives a restart, private messages stay private, database restore is exercised, and the pause control works. Validate the pilot with a real trip and an ordinary week. Recheck dates before treating any trip in the interview as upcoming.

M5: Add the metered model gateway and role proposals.

Introduce provider SDK, structured schemas, source references, reservations, redaction, and the fake model test double. First enable trip extraction and useful briefing synthesis. Add other role capabilities only when their data is available. Keep deterministic reminders available if the model is absent or the paid-AI budget is exhausted.

Acceptance: malformed output is rejected; missing flight times remain missing; embedded source instructions cannot change audience or authorization; unsupported claims appear as unresolved; concurrent requests respect the budget; provider errors have useful fallbacks.

M6: Add one read-only integration at a time.

Start with selected personal confirmations or calendar availability, according to actual accessible accounts. Add connection-status UI, read-only probes, consent, encrypted tokens, revocation, cursors, and freshness. Validate invitation updates in a real Outlook client before claiming the calendar bridge works.

Acceptance: a current successful authorized request demonstrates each claimed capability; repeated sync does not duplicate records; changed/deleted sources are reconciled; work content remains outside the personal workflow; an expired/revoked credential produces an actionable state.

M7: Complete specialist workflows incrementally.

Add home and pet-care schedules, social/birthday planning, fitness summaries, and annual budget scenarios. Provide simple forms/imports before integrating app-specific APIs. Keep appointment booking as a tracked manual/draft task where a provider has no supported route. Use a selected year rather than hard-coding the first requested budget year into business logic.

Acceptance: each enabled role produces at least one useful end-to-end output using actual authorized or synthetic data, with appropriate audience and approval rules. Financial calculations are deterministic and balance; health summaries retain units, timestamps, sources, and missing-data indicators; gift surprises remain private.

M8: Add narrowly authorized external actions and evaluate optional messaging.

Select one routine workflow with a supported execution path, clear limits, an explicit affected-person owner, and verifiable provider results. Reuse the existing policy engine and state machine. Confirm capability, terms, total cost, and outcome handling before live execution. For scheduling, missing or stale availability is unknown, not free time; use a current authorized availability source or an explicitly confirmed slot. Assess shared messaging as a separate adapter after verifying current group support and costs.

Acceptance: dry-run tests and one authorized live result demonstrate the selected capability; stale approval or unknown outcome prevents duplicate execution; rollback/cancellation behavior is documented. Unsupported booking, phone, payment, or messaging routes remain visible manual tasks.

Meaningful tests to implement:

| Test file | Required behavior |
| --- | --- |
| test_access.py | Private and cross-household records cannot leak through pages, jobs, exports, linked sources, or model context. |
| test_scheduling.py | A local morning schedule remains at the same local time over both DST changes; edits retire old work; early events get preparation before their start. |
| test_worker.py | PostgreSQL TransactionTestCase exercises two claimers, expired leases before/after possible submission, bounded retries, cancellation, and restart recovery without duplicate external execution. |
| test_briefings.py | Shared/private content and recipients are correct; both members' private occurrences coexist; a source made private after queueing cannot leak; stale/missing data is explicit; there is no dependency on AI. |
| test_actions.py | Full-price boundaries, ownership, approval revision binding, duplicate clicks, expired quotes, and ambiguous provider outcomes are enforced. |
| test_budget.py | Concurrent reservations cannot oversubscribe the allowance; fixed and unknown costs are handled; unused reservations reconcile safely. |
| test_imports.py | Duplicates, prompt-injection text, malformed dates, changed confirmations, currency/units, and missing fields are handled. |
| test_connectors.py | Fake and live-adapter contracts distinguish configured, authenticated, attempted, accepted, and confirmed states. |
| test_mobile_flow.py | One browser flow covers login, a shared/private plan, briefing preview, and review of a proposal on a narrow viewport. |

Use Django's test runner and PostgreSQL for domain/concurrency tests. Add Playwright for the small browser flow when the UI exists; avoid a parallel JavaScript build toolchain just for tests. Use Ruff for linting. Do not use live paid APIs or real external sends in CI. Add focused tests for behavior and failure cases, not tests that simply mirror a function's internal implementation.

The expected local verification commands, once scaffolding exists, are:

    uv sync --locked
    uv run python manage.py check
    uv run python manage.py migrate --check
    uv run python manage.py makemigrations --check --dry-run
    uv run python manage.py test
    uv run ruff check .

Document the chosen database startup command and required variables alongside those commands. Do not silently substitute SQLite for concurrency validation. If PostgreSQL cannot start, diagnose the environment and report the unrun PostgreSQL tests accurately while continuing independent work.

Production configuration includes DATABASE_URL, Django secret/hosts/origin settings, a private encryption key when connectors are added, email transport settings, worker lease/poll settings, outbound mode, and model provider/model/key settings. Use an application-prefixed API-key variable such as WORKFORCE_LLM_API_KEY if the platform reserves provider-standard names. Store secret values in the supported secret manager, never this document or chat.

At launch, require explicit production settings: DEBUG false, secure cookies, HTTPS origins, no demo identities, persistent PostgreSQL, valid timezones, configured backup storage, and known external-action mode. Health checks must not expose credentials or household data. Monitor worker heartbeat, oldest due job, last successful delivery, ambiguous outcomes, connection expiry, and current budget.

Before purchasing services, ask about existing subscriptions/accounts. ChatGPT and Claude plans do not establish separately billed API entitlement or capacity. Current vendor pricing and several official integration documents were inaccessible from the onboarding environment; verify them through authorized access before promising a capability or enrolling in a paid service. Do not work around network policy or invent successful checks.

The coding environment is not the deployed morning-briefing service. When setup commands actually exist and have been exercised, save the necessary cloud install/start instructions through the onboarding configuration tools, using the applicable setup skill. An untested script in a draft does not establish runtime readiness.

Definition of done for the first pilot: both intended users can access the application; private and shared records behave correctly; the morning briefing is delivered through the agreed channel at the intended local time; real itinerary facts drive useful preparation; approval and cost boundaries work; restart recovery and restore are demonstrated; and operational limitations are visible. Continue expanding only after this slice works.
