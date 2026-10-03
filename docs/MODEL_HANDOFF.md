Continuation instructions for the next coding model

M0–M3 are implemented and tested. Read docs/BUILD_STATUS.md for current evidence. The next milestone is M4, which needs actual sender, recipient, subscription-cost, and hosting configuration. The application remains preview-only.

Read docs/IMPLEMENTATION_PLAN.md first. Then, if present in the same workspace, read /workspace/personal-workforce-design.md for the private household requirements. That private file belongs outside this public checkout. If it is absent in a new environment, use the conversation's authorized requirements; do not invent missing personal facts or copy sensitive information into public fixtures.

The repository at /workspace/codex initially contained only readme.md. Its branch is main. Use this existing checkout. No separate worktree is required.

The fixed engineering approach is Python 3.12, Django 5.2 LTS, PostgreSQL 16, uv, server-rendered mobile-friendly pages, and a database-backed worker. Eight roles share this application. Do not restart architecture selection merely because the implementation model changed.

The user has accepted email as the first delivery channel. Existing subscriptions are recorded in the private brief; their plan tiers and actual monthly prices remain unknown. Ask when needed before paid activation, and first check whether existing services can satisfy a requirement. Missing credentials do not block the local fake-transport build.

The first local deliverable already covers project setup, invited membership, shared/private planning, trip details, deterministic briefing preview, durable jobs, fake email, approvals, and budgets. Preserve this implementation and its acceptance tests. Continue with the next authorized milestone; account integrations and live delivery require the specific secure account configuration described in M4. Runtime settings currently reject live delivery and paid AI.

Work in bounded milestones:

1. Inspect the current Git status and any agent instructions. Preserve the user's files.
2. Read docs/BUILD_STATUS.md if it exists; otherwise create it with every milestone marked not started.
3. State which milestone is being implemented and its acceptance gate.
4. Implement the smallest complete path, including meaningful failure handling.
5. Run the milestone's relevant checks. Preserve actual exit statuses and distinguish passed, failed, and unrun checks.
6. Update BUILD_STATUS with the completed behavior, commands/results, remaining gaps, and the exact next task. Do not put personal data or secrets in that public status file.
7. Continue the next authorized, independent milestone. Ask only for the precise missing prerequisite when it prevents dependent work; continue unaffected implementation.

Non-negotiable behavior:

- All private-data filtering happens before rendering, export, or model calls, and queued output is revalidated before sending.
- Only deterministic code grants permissions, resolves recipients, approves spending policy, and commits external actions.
- Unknown times, costs, outcomes, and capabilities remain unknown.
- A timed-out external action or expired worker lease may hide a successful submission; reconcile before retrying.
- Local-time scheduling uses IANA timezones and durable occurrence keys that distinguish each private recipient.
- Spending approval binds the exact proposal, amount, terms, affected people, and revision.
- The application budget includes fixed subscriptions and metered services; consumer chat plans are not assumed to include API credits.
- Preserve the existing health apps. Use supported exports/API routes as verified.
- The household's work-managed calendars do not authorize work-email or work-meeting ingestion.
- Shared group messaging and phone/app-only bookings are unverified capabilities.
- Never claim email delivery, calendar acceptance, or a provider booking based only on a mock, queued job, or model statement.
- This repository is public. All demonstrations, snapshots, tests, and example configurations use fictional data.

M4 introduces live sender configuration and deployment. Collect specific account information through supported secure flows only after the local deliverable is concrete. Show the actual service choices and costs before new subscriptions or deployment. Verify authorized recipients before any live test send. Do not enable real purchasing connectors as part of the initial build.

Consult the private brief at that point for the actual household approval and monthly-budget values. If the user changes them in conversation, update private runtime configuration and associated behavior, not public fixtures containing their real profile.

Do not ask the user to learn coding tools. Explain progress in terms of what they can now do, what was tested, and which specific decision or account connection is needed next.
