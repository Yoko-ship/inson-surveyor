"""Serve the local Mini App over a temporary HTTPS tunnel for the pinned bot."""

import asyncio
import fcntl
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
runtime = ROOT / "data" / "telegram-dev"
runtime.mkdir(parents=True, exist_ok=True)
lock = (runtime / "runner.lock").open("w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Telegram development runner is already active") from None
env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}}
if env.get("DATA_MODE", "synthetic") != "synthetic":
    raise SystemExit("Temporary Telegram development tunnels require DATA_MODE=synthetic")
if not env.get("TELEGRAM_BOT_TOKEN") or not env.get("TELEGRAM_EXPECTED_BOT_ID"):
    raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_EXPECTED_BOT_ID in .env first")
binary = shutil.which("cloudflared") or str(ROOT / ".tools" / "cloudflared")
if not Path(binary).is_file():
    raise SystemExit("Run: uv run python scripts/install_cloudflared.py")
port = int(env.get("TELEGRAM_DEV_PORT", "8012"))
with socket.socket() as sock:
    if sock.connect_ex(("127.0.0.1", port)) == 0:
        raise SystemExit(f"Port {port} is already occupied; no processes were stopped")
processes = []
url = None
configured = False


def stop(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


async def cleanup_webhook():
    from surveyor.telegram import call_telegram
    from surveyor.telegram_setup import set_menu, verify_identity

    await verify_identity()
    info = await call_telegram("getWebhookInfo")
    if info.get("url") == url + "/telegram/webhook":
        await call_telegram("deleteWebhook", json={"drop_pending_updates": False})
        await set_menu({"type": "commands"})


try:
    with (runtime / "cloudflared.log").open("w") as log:
        tunnel = subprocess.Popen(
            [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"], stdout=log, stderr=log
        )
        processes.append(tunnel)
        for _ in range(60):
            match = re.search(
                r"https://[a-z0-9-]+\.trycloudflare\.com", (runtime / "cloudflared.log").read_text()
            )
            if match:
                url = match.group()
                break
            if tunnel.poll() is not None:
                raise RuntimeError("Tunnel process stopped; see data/telegram-dev/cloudflared.log")
            time.sleep(1)
        if not url:
            raise RuntimeError("Tunnel URL was not ready in 60 seconds")
        env.update(PUBLIC_URL=url, COOKIE_SECURE="true", COOKIE_SAMESITE="none", APP_ENV="production")
        os.environ.update(env)
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        with (runtime / "app.log").open("w") as app_log:
            app = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "surveyor.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                    "--reload",
                    "--reload-dir",
                    str(ROOT / "surveyor"),
                ],
                env=env,
                stdout=app_log,
                stderr=app_log,
            )
            processes.append(app)
            with httpx.Client(timeout=5) as client:
                last_error = "not ready"
                for attempt in range(120):
                    try:
                        response = client.get(url + "/health")
                        last_error = f"HTTP {response.status_code}"
                        if response.status_code == 200 and response.json().get("status") == "ok":
                            break
                    except (httpx.HTTPError, ValueError) as exc:
                        last_error = type(exc).__name__
                    if attempt % 20 == 0:
                        print(f"Waiting for temporary HTTPS endpoint: {last_error}", flush=True)
                    if app.poll() is not None:
                        raise RuntimeError("App process stopped; see data/telegram-dev/app.log")
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Public HTTPS health check failed: {last_error}")
            from surveyor.telegram_setup import configure_webhook

            configured = True
            bot = asyncio.run(configure_webhook())
            status = {"url": url, "bot": bot["username"], "pid": os.getpid(), "port": port}
            (runtime / "status.json").write_text(json.dumps(status, indent=2))
            print(f"Telegram ready: https://t.me/{bot['username']}", flush=True)
            print(f"Temporary Mini App URL: {url}", flush=True)
            print(
                "Keep this process and your Mac running. Ctrl+C stops the tunnel and removes its webhook.",
                flush=True,
            )
            while app.poll() is None and tunnel.poll() is None:
                time.sleep(2)
            raise RuntimeError("A development process stopped; restart the runner")
except KeyboardInterrupt:
    print("Stopping Telegram development session", flush=True)
finally:
    if configured:
        try:
            asyncio.run(cleanup_webhook())
        except Exception:
            print("Could not clear the development webhook; inspect it before restarting", flush=True)
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    (runtime / "status.json").unlink(missing_ok=True)
