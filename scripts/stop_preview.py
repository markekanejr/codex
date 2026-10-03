"""Stop only the web/worker processes recorded for this checkout."""

import json
import os
import signal
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
state_path = root / "private/runtime.json"
if state_path.exists():
    state = json.loads(state_path.read_text())
    for name, pid in state.items():
        path = Path(f"/proc/{pid}/cmdline")
        if path.exists():
            command = path.read_bytes()
            expected = b"runserver" if name == "web" else b"run_worker"
            if str(root / "manage.py").encode() in command and expected in command:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
    for _ in range(20):
        if all(
            not Path(f"/proc/{pid}/cmdline").exists()
            or not Path(f"/proc/{pid}/cmdline").read_bytes()
            for pid in state.values()
        ):
            break
        time.sleep(0.1)
    state_path.unlink()
print("This checkout's preview processes are stopped.")
