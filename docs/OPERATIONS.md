Preview operation

This build implements M0–M3. It uses PostgreSQL 16 and Django 5.2. Delivery and actions are previews only; there are no live email, payment, booking, or model adapters.

From the checkout, initialize or refresh dependencies and the local database:

    sh scripts/setup_preview.sh

The script preserves existing configuration, generates random development credentials only when needed, installs the dependency lock, starts PostgreSQL, and applies migrations. Ignored .env and .db.env files are private. The Docker volume retains data in the current machine; do not assume an onboarding snapshot also captures that volume. Actual household data belongs in the managed database/backup setup planned for M4.

Start the web application and worker:

    uv run python scripts/start_preview.py

The helper records its own process IDs in ignored private/runtime.json and reuses only matching processes from this checkout. Logs are private. It checks the health response and login page. Morning previews are scheduled in the household's IANA timezone. An expired worker lease after possible submission is an unknown outcome, not permission to retry.

After code changes, restart only these processes:

    uv run python scripts/stop_preview.py
    uv run python scripts/start_preview.py

For foreground debugging instead:

    uv run python manage.py runserver 127.0.0.1:8000 --noreload
    uv run python manage.py run_worker --poll 5

Use separate sessions for these commands; check the helper's recorded processes first to avoid duplicates.

Create a fictional development household without passwords:

    uv run python manage.py load_demo

This command refuses production settings and preserves existing records. Demo identities have unusable passwords by default. To create an initial actual account, use bootstrap_household with a privately provided email and household name; the command requests a password without echoing it. Never put passwords in command arguments. To regain access in preview mode, use Django's changepassword command with the account email. Password-reset messages are generated only in process memory and are not delivered.

After sign-in, use Settings to create a single-use partner invitation. Share its link privately; it expires in 24 hours. Each member owns their private records. Shared visibility does not grant edit authority over another person's plans.

Overview shows shared and individual previews. Itinerary fields can remain unknown. Airport reminders require confirmed flight timing and configured buffers. A proposed plan is visibly distinct from a confirmed commitment.

Review provides price checks, exact authenticated approvals, and simulated execution. Full USD totals include fees. Routine policies apply only to the owner's own commitments and the named vendor. Over-threshold proposals require the designated pricing approver. Private partner proposals do not become visible to that approver automatically.

Tools budget records subscription costs separately from usage. Unknown commitments and an unconfirmed inventory block usage reservations. Paid AI is globally disabled in this release even if budget data is complete.

Verification commands:

    uv sync --locked
    uv run python manage.py check
    uv run python manage.py migrate --check
    uv run python manage.py makemigrations --check --dry-run
    uv run python manage.py test
    uv run ruff check .
    uv run ruff format --check .

Tests use PostgreSQL, including threaded concurrency checks. The mobile flow uses the system Chromium at /usr/bin/chromium with Playwright; configure a trusted executable at that path in a new environment before running the browser test. No paid API calls or real sends occur in tests. A screenshot of fictional data is written to /tmp/workforce-mobile-preview.png.

No application data or credentials should enter the public checkout, fixtures, screenshots, or Git history. Actual configuration and provider access are the next milestone's prerequisites. A development server and preview worker in this coding workspace are not the continuously deployed service planned for M4.
