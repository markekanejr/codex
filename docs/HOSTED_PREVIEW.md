Hosted preview on Render

The hosted preview remains invite-only and simulated. No live email, messages, purchases, bookings, or paid model calls are enabled. Hosting is a partial M4 task, not completion of M4.

Prepared resources: a paid Starter Docker web service, a paid Starter Docker background worker, and a managed Basic PostgreSQL database. Current prices and availability are unverified because this workspace cannot access Render's documentation or pricing. Review the dashboard's combined monthly quote, including storage and any additional charges, before creating resources. Count hosting alongside existing AI subscriptions in the household tools budget. Do not treat unknown costs as zero.

Account steps for the owner:

1. Open https://render.com and create or sign into your account. Connect GitHub and allow access to this application repository only.
2. Create a Blueprint from the application repository and the household-preview branch. Render should discover render.yaml. Review its validation and resource quote before deploying. If the declared plans have changed, resolve them against the dashboard's current offerings first.
3. Deploy after reviewing the quote. Keep all preview and paid-AI switches as declared. Never paste credentials into this public repository or chat. Render generates the Django secret and supplies the internal database URL.
4. Verify the release migration succeeds before relying on the worker. An initial worker may restart while the web release first creates the database tables. Check both services become healthy. Verify the database has no public ingress and inspect its backup/retention settings.
5. In the web service's private Shell, create the initial account with `python manage.py bootstrap_household --email YOUR_PERSONAL_EMAIL`. It requests the password twice without displaying it. This preview has no functioning email password recovery; use `python manage.py changepassword YOUR_PERSONAL_EMAIL` in the private Shell if necessary.
6. Open the web service's HTTPS address on the iPhone. Log in and use Settings to invite the partner. Share the invitation privately; it expires after 24 hours. Do not create real data until production access and backup checks are complete.

The web image uses Gunicorn and WhiteNoise with production settings, secure cookies, HTTPS redirects, and explicit allowed hosts. Render's injected RENDER_EXTERNAL_HOSTNAME permits the generated domain. Custom domains require explicit DJANGO_ALLOWED_HOSTS and, when appropriate, DJANGO_CSRF_TRUSTED_ORIGINS. Trust forwarded HTTPS headers only behind Render's controlled proxy, never on a publicly exposed direct application port. HSTS applies to the preview hostname without preloading or covering provider-owned subdomains.

Provider-generated secret inputs must have at least 32 characters and adequate variety. Valid inputs below 50 characters are expanded deterministically by a domain-separated SHA-256 hash for Django's length heuristic; this does not add entropy. The web and worker use the same derivation. Existing longer inputs remain unchanged. The initial remote build succeeded but pre-deploy exposed the former 50-character rejection; this is fixed and tested with 68 passing tests. Redeploy the existing services rather than creating duplicate resources.

The pre-deploy command runs migrations once per web release. The worker never migrates. Validate /health/, login, CSS, and the signed-in overview after each deployment; /health/ is a process liveness endpoint, not a database or schema readiness guarantee. Do not put personal request bodies, invitation URLs, or export data in deployment logs. Gunicorn access logs are disabled by default.

Backup before upgrades: use the managed provider's protected database export/backup tools. Confirm retention in the selected plan; no scheduled backup or restore has been verified yet. Restore to a separate database first, stop the worker, use the restored database with preview settings, verify migration status and shared/private records with authorized household accounts, then resume. Do not commit backup files. A restore may replay earlier pending simulated jobs; do not enable live delivery during a restore.

Local validation: 65 tests passed, including browser workflow, HTTPS redirect, secure CSRF cookie, and hostname rejection. Production deploy checks and a Gunicorn smoke test passed for health, protected home, login, hashed CSS, and private cache headers. Full Docker image build remains unverified: this workspace's Docker build container cannot resolve the package index, including with host networking. Render's actual blueprint validation, container build, migrations, HTTPS address, service availability, and backup/restore all still require deployment verification.
