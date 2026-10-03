"""Start only this checkout's web/worker processes and verify local HTTP readiness."""

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "private"
PRIVATE.mkdir(exist_ok=True, mode=0o700)
STATE = PRIVATE / "runtime.json"
state = json.loads(STATE.read_text()) if STATE.exists() else {}
env = os.environ.copy()
env["WORKFORCE_OUTBOUND_MODE"] = "preview"
env["WORKFORCE_PAID_AI"] = "false"

for name, arguments in {
    "web": ["runserver", "127.0.0.1:8000", "--noreload"],
    "worker": ["run_worker", "--poll", "5"],
}.items():
    pid = state.get(name)
    cmdline = Path(f"/proc/{pid}/cmdline")
    valid = False
    if pid and cmdline.exists():
        command = cmdline.read_bytes()
        valid = str(ROOT / "manage.py").encode() in command and arguments[0].encode() in command
    if not valid:
        logfile = PRIVATE / f"{name}.log"
        with logfile.open("ab") as output:
            os.chmod(logfile, 0o600)
            process = subprocess.Popen(
                [str(ROOT / ".venv/bin/python"), str(ROOT / "manage.py"), *arguments],
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        state[name] = process.pid

STATE.write_text(json.dumps(state))
os.chmod(STATE, 0o600)
for _ in range(30):
    try:
        with urlopen("http://127.0.0.1:8000/health/", timeout=2) as response:
            assert response.read() == b"ok"
        with urlopen("http://127.0.0.1:8000/accounts/login/", timeout=2) as response:
            assert b"Welcome back" in response.read()
        if not all(Path(f"/proc/{pid}/cmdline").exists() for pid in state.values()):
            raise RuntimeError("A preview process exited.")
        print("Preview web service, login page, and worker are ready.")
        break
    except (OSError, AssertionError, RuntimeError):
        time.sleep(0.5)
else:
    raise SystemExit("Preview startup failed. Inspect the private web/worker logs.")
