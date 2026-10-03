"""Create ignored, random local credentials once. Never overwrite user configuration."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
db_path = root / ".db.env"
app_path = root / ".env"
if app_path.exists() and not db_path.exists():
    raise SystemExit(
        "Existing .env found. Configure .db.env to match it; no files were overwritten."
    )
if not db_path.exists():
    password = secrets.token_urlsafe(32)
    db_path.write_text(
        f"POSTGRES_DB=workforce\nPOSTGRES_USER=workforce\nPOSTGRES_PASSWORD={password}\n"
    )
    os.chmod(db_path, 0o600)
db_vars = dict(line.split("=", 1) for line in db_path.read_text().splitlines() if "=" in line)
if not app_path.exists():
    app_path.write_text(
        "DJANGO_DEBUG=true\n"
        f"DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}\n"
        "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver\n"
        f"DATABASE_URL=postgresql://workforce:{db_vars['POSTGRES_PASSWORD']}@127.0.0.1:54328/workforce\n"
        "WORKFORCE_OUTBOUND_MODE=preview\nWORKFORCE_PAID_AI=false\n"
    )
    os.chmod(app_path, 0o600)
print("Local configuration ready. Existing files preserved.")
