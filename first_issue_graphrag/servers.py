#!/usr/bin/env python3
"""Start, stop and check the app's two servers. Works on Linux, macOS and Windows.

    python first_issue_graphrag/servers.py start          # backend + frontend (dev)
    python first_issue_graphrag/servers.py start --prod   # frontend as a production build
    python first_issue_graphrag/servers.py start --lan    # frontend reachable from other devices
    python first_issue_graphrag/servers.py status
    python first_issue_graphrag/servers.py stop

Run it with the project's virtual environment active: the backend starts with the
same interpreter that runs this script. Node.js and npm must be on PATH.

* Backend: FastAPI on 127.0.0.1:8090. It is never exposed; the browser reaches it
  through the frontend's /api proxy.
* Frontend: Next.js on 127.0.0.1:3000, or on all interfaces with --lan. With --lan
  in dev mode, also set ALLOWED_DEV_ORIGINS (see frontend/.env.example).

Neo4j and Weaviate must already be running; this script does not start them.
Logs and process ids go to first_issue_graphrag/.run/ (git-ignored).
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR / "backend"
FRONTEND_DIR = APP_DIR / "frontend"
RUN_DIR = APP_DIR / ".run"
BACKEND_PORT = int(os.getenv("API_PORT", "8090"))
FRONTEND_PORT = 3000
IS_WINDOWS = os.name == "nt"
SERVICES = ("backend", "frontend")


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def pid_file(name: str) -> Path:
    return RUN_DIR / f"{name}.pid"


def read_pid(name: str) -> int | None:
    try:
        return int(pid_file(name).read_text().strip())
    except (OSError, ValueError):
        return None


def alive(pid: int) -> bool:
    if IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def spawn(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    """Start a detached process whose output goes to .run/<name>.log; return its pid."""
    RUN_DIR.mkdir(exist_ok=True)
    log = open(RUN_DIR / f"{name}.log", "ab")
    kwargs: dict = {"cwd": str(cwd), "env": env, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True  # own process group, so stop can end the whole tree
    proc = subprocess.Popen(cmd, **kwargs)
    pid_file(name).write_text(str(proc.pid))
    return proc.pid


def kill_tree(pid: int) -> None:
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(50):
        if not alive(pid):
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def wait_for_port(port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def npm() -> str:
    exe = shutil.which("npm")  # resolves npm.cmd on Windows
    if not exe:
        sys.exit("npm was not found on PATH. Install Node.js 20 or newer.")
    return exe


def start(args: argparse.Namespace) -> int:
    for name, port in (("backend", BACKEND_PORT), ("frontend", FRONTEND_PORT)):
        if port_open(port):
            sys.exit(f"Port {port} is already in use ({name}). Run `servers.py stop` or free the port.")
    if not (FRONTEND_DIR / "node_modules").is_dir():
        sys.exit("frontend/node_modules is missing. Run `npm ci` in first_issue_graphrag/frontend first.")

    env = dict(os.environ)
    spawn("backend", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
          BACKEND_DIR, env)
    print(f"backend  starting on http://127.0.0.1:{BACKEND_PORT}")

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if args.prod:
        print("frontend building (next build) ...")
        built = subprocess.run([npm(), "run", "build"], cwd=str(FRONTEND_DIR), env=env)
        if built.returncode != 0:
            stop(args)
            sys.exit("The frontend build failed.")
    script = "start" if args.prod else "dev"
    spawn("frontend", [npm(), "exec", "--", "next", script, "-H", host, "-p", str(FRONTEND_PORT)], FRONTEND_DIR, env)
    print(f"frontend starting on http://{host}:{FRONTEND_PORT} ({'production' if args.prod else 'dev'})")

    ok_back = wait_for_port(BACKEND_PORT, 60)
    ok_front = wait_for_port(FRONTEND_PORT, 120)
    print()
    status(args)
    if not (ok_back and ok_front):
        print(f"\nA server did not come up. See the logs in {RUN_DIR}")
        return 1
    print(f"\nOpen http://localhost:{FRONTEND_PORT}/research")
    return 0


def stop(_args: argparse.Namespace) -> int:
    for name in SERVICES:
        pid = read_pid(name)
        if pid and alive(pid):
            kill_tree(pid)
            print(f"{name:<9}stopped (pid {pid})")
        else:
            print(f"{name:<9}not running")
        pid_file(name).unlink(missing_ok=True)
    return 0


def status(_args: argparse.Namespace) -> int:
    for name, port in (("backend", BACKEND_PORT), ("frontend", FRONTEND_PORT)):
        pid = read_pid(name)
        running = bool(pid and alive(pid))
        state = f"pid {pid}" if running else "no process started by this script"
        print(f"{name:<9}port {port}: {'listening' if port_open(port) else 'closed'} ({state})")
    if port_open(BACKEND_PORT):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=30) as resp:
                health = json.loads(resp.read())
            print("health   " + ", ".join(f"{k}={health.get(k)}" for k in ("neo4j", "weaviate", "graph_populated")))
        except Exception as exc:  # the API is up but a database probe failed or timed out
            print(f"health   not available ({type(exc).__name__})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Start, stop and check the backend and frontend.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_start = sub.add_parser("start", help="start backend and frontend in the background")
    p_start.add_argument("--prod", action="store_true", help="build the frontend and serve the production build")
    p_start.add_argument("--lan", action="store_true", help="serve the frontend on all network interfaces")
    p_start.set_defaults(func=start)
    sub.add_parser("stop", help="stop the servers this script started").set_defaults(func=stop)
    sub.add_parser("status", help="show ports, processes and API health").set_defaults(func=status)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
