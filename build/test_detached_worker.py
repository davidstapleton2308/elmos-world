"""Windows CI: exercise the SAME hidden update subprocess launcher used in production.

This is deliberately not run during source unittest discovery; it requires a
compiled installer and desktop executable, and executes the installer twice.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))
import update_center


def main():
    if sys.platform != 'win32':
        raise RuntimeError('This integration test requires Windows.')
    if len(sys.argv) != 3:
        raise RuntimeError('Usage: test_detached_worker.py SETUP_EXE INSTALLED_APP_EXE')
    installer = Path(sys.argv[1]).resolve()
    app = Path(sys.argv[2]).resolve()
    if not installer.is_file() or not app.is_file():
        raise RuntimeError('Installer or installed application does not exist.')
    with tempfile.TemporaryDirectory(prefix='elmos-worker-ci-') as directory:
        update_center.CFG = Path(directory) / 'update_center.json'
        # Simulate the installed frozen app which owns the helper process.
        sys.frozen = True
        sys.executable = str(app)
        # Already-exited parent PID is intentional; never wait for CI test Python.
        worker_pid = update_center.launch_helper(installer, 2147483600)
        print('Worker process started and acknowledged startup; PID', worker_pid, flush=True)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            state = update_center.last_attempt() or {}
            if state.get('state') in ('complete', 'failed'):
                print('Worker outcome:', json.dumps(state), flush=True)
                if state['state'] != 'complete':
                    log_path = Path(directory) / 'logs' / 'update.log'
                    if log_path.exists():
                        print(log_path.read_text(encoding='utf-8-sig', errors='replace')[-4000:])
                    raise RuntimeError('Detached background update did not succeed.')
                return
            time.sleep(0.5)
        raise RuntimeError('Detached background updater did not complete within 150 seconds.')


if __name__ == '__main__':
    main()
