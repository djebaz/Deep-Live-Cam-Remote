#!/usr/bin/env python3
"""Start the browser remote controller on this PC with one command.

Checks Node and Tailscale, finds your online Colab machine, installs/builds the web
app only when needed, keeps a per-user gateway token, starts the private gateway in
the background and publishes it on your tailnet with ``tailscale serve``.

    python scripts/start_web_controller.py                 # start (or restart)
    python scripts/start_web_controller.py --backend 100.110.24.125:7860
    python scripts/start_web_controller.py --status
    python scripts/start_web_controller.py --stop
    python scripts/start_web_controller.py --install-autostart   # Windows login

Standard library only, so any Python 3.10+ can run it.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = REPO_ROOT / "web_app"
APP_NAME = "DeepLiveCamRemote"
MIN_NODE = (22, 12)
IS_WINDOWS = os.name == "nt"
STARTUP_NAME = "DeepLiveCamWebController.cmd"


class LauncherError(Exception):
    """A problem the user can fix; printed without a traceback."""


# --------------------------------------------------------------------------- paths
def state_dir() -> Path:
    override = os.environ.get("DLCR_STATE_DIR")
    if override:
        base = Path(override)
    elif IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def startup_script_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not IS_WINDOWS or not appdata:
        raise LauncherError("Autostart is only supported on Windows.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_NAME


# --------------------------------------------------------------------------- helpers
def say(message: str) -> None:
    print(message, flush=True)


def step(message: str) -> None:
    say(f"==> {message}")


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def find_tool(name: str, hint: str) -> str:
    path = shutil.which(name)
    if not path:
        raise LauncherError(f"{name} not found. {hint}")
    return path


def parse_node_version(text: str) -> tuple[int, int]:
    match = re.match(r"v?(\d+)\.(\d+)", text.strip())
    if not match:
        raise LauncherError(f"Could not read the Node version from {text!r}.")
    return int(match.group(1)), int(match.group(2))


def check_node() -> tuple[str, str]:
    hint = "Install Node 22.12+ or 24 from https://nodejs.org"
    node, npm = find_tool("node", hint), find_tool("npm", hint)
    version = parse_node_version(run([node, "--version"]).stdout)
    if version < MIN_NODE:
        raise LauncherError(f"Node {version[0]}.{version[1]} is too old; need {MIN_NODE[0]}.{MIN_NODE[1]} or newer.")
    return node, npm


# --------------------------------------------------------------------------- tailscale
def tailscale_status() -> dict[str, Any]:
    exe = find_tool("tailscale", "Install Tailscale and sign in: https://tailscale.com/download")
    result = run([exe, "status", "--json"])
    if result.returncode != 0:
        raise LauncherError(f"tailscale status failed: {(result.stderr or result.stdout).strip()}")
    status = json.loads(result.stdout)
    if status.get("BackendState") != "Running":
        raise LauncherError(f"Tailscale is not running (state: {status.get('BackendState')}). Start it and sign in.")
    return status


def self_dns_name(status: dict[str, Any]) -> str:
    name = str(status.get("Self", {}).get("DNSName", "")).rstrip(".")
    if not name:
        raise LauncherError("No Tailscale DNS name. Enable MagicDNS in the Tailscale admin console (DNS page).")
    return name


def pick_colab_backend(status: dict[str, Any], port: int) -> tuple[str, list[str]]:
    """Return (host:port, names of all online Colab machines) for the newest online one."""
    peers = [
        peer for peer in (status.get("Peer") or {}).values()
        if peer.get("Online") and (
            str(peer.get("HostName", "")).lower().startswith("colab")
            or str(peer.get("DNSName", "")).lower().startswith("colab")
        )
    ]
    if not peers:
        raise LauncherError(
            "No online Tailscale machine named 'colab*'. Start the Colab notebook (with Tailscale) "
            "or pass --backend <ip>[:port]."
        )
    peers.sort(key=lambda peer: str(peer.get("Created", "")), reverse=True)
    chosen = peers[0]
    ips = [ip for ip in chosen.get("TailscaleIPs", []) if ":" not in ip]
    if not ips:
        raise LauncherError(f"Colab machine {chosen.get('HostName')} has no IPv4 Tailscale address.")
    return f"{ips[0]}:{port}", [str(peer.get("HostName")) for peer in peers]


def resolve_backend(status: dict[str, Any], explicit: str | None, default_port: int) -> str:
    if explicit:
        target = re.sub(r"^https?://", "", explicit).strip("/")
        return target if re.search(r":\d+$", target) else f"{target}:{default_port}"
    target, names = pick_colab_backend(status, default_port)
    if len(names) > 1:
        say(f"Several Colab machines are online: {', '.join(names)}. Using the newest; pass --backend to choose.")
    say(f"Colab backend: {target}")
    return target


# --------------------------------------------------------------------------- build
def newest_mtime(paths: list[Path]) -> float:
    newest = 0.0
    for path in paths:
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    newest = max(newest, child.stat().st_mtime)
    return newest


def needs_install(web_root: Path) -> bool:
    marker = web_root / "node_modules" / ".package-lock.json"
    lock = web_root / "package-lock.json"
    return not marker.exists() or lock.stat().st_mtime > marker.stat().st_mtime


def needs_build(web_root: Path, force: bool = False) -> bool:
    dist = web_root / "dist" / "index.html"
    if force or not dist.exists():
        return True
    sources = [web_root / name for name in ("src", "index.html", "package.json", "tsconfig.json")]
    return newest_mtime(sources) > dist.stat().st_mtime


def update_web_app(npm: str, rebuild: bool) -> None:
    if needs_install(WEB_ROOT):
        step("Installing web dependencies (npm ci)")
        subprocess.run([npm, "--prefix", str(WEB_ROOT), "ci", "--no-audit", "--no-fund"], check=True)
    if needs_build(WEB_ROOT, rebuild):
        step("Building the web app")
        subprocess.run([npm, "--prefix", str(WEB_ROOT), "run", "build"], check=True)


# --------------------------------------------------------------------------- token
def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise OSError("Windows DPAPI call failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)  # type: ignore[attr-defined]


def encode_token(token: str) -> str:
    if IS_WINDOWS:
        try:
            return "dpapi:" + base64.b64encode(_dpapi(token.encode(), True)).decode()
        except Exception:
            say("Could not protect the token with Windows DPAPI; storing it as plain text in your profile.")
    return "plain:" + token


def decode_token(stored: str) -> str:
    kind, _, value = stored.strip().partition(":")
    if kind == "dpapi":
        return _dpapi(base64.b64decode(value), False).decode()
    if kind == "plain" and value:
        return value
    raise ValueError("unrecognised token file")


def new_token() -> str:
    return secrets.token_urlsafe(30)


def load_or_create_token(directory: Path, rotate: bool) -> str:
    file = directory / "web-gateway.token"
    if not rotate and file.exists():
        try:
            token = decode_token(file.read_text())
            if len(token) >= 24:
                return token
        except Exception:
            say("Saved token could not be read; creating a new one.")
    token = new_token()
    file.write_text(encode_token(token))
    try:
        file.chmod(0o600)
    except OSError:
        pass
    return token


# --------------------------------------------------------------------------- gateway process
def pid_file() -> Path:
    return state_dir() / "web-gateway.pid"


def is_our_gateway(pid: int) -> bool:
    """True only for a live node process; guards against a stale PID file killing something else."""
    if IS_WINDOWS:
        out = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]).stdout.lower()
        return "node" in out
    out = run(["ps", "-p", str(pid), "-o", "command="]).stdout
    return "gateway.mjs" in out


def read_pid() -> int | None:
    try:
        return int(pid_file().read_text().strip())
    except (OSError, ValueError):
        return None


def running_gateway() -> int | None:
    pid = read_pid()
    if pid is not None and is_our_gateway(pid):
        return pid
    pid_file().unlink(missing_ok=True)
    return None


def stop_gateway() -> bool:
    pid = running_gateway()
    if pid is None:
        return False
    step(f"Stopping the gateway (PID {pid})")
    if IS_WINDOWS:
        run(["taskkill", "/PID", str(pid), "/T", "/F"])
    else:
        os.kill(pid, 15)
        for _ in range(20):
            if not is_our_gateway(pid):
                break
            time.sleep(0.25)
    pid_file().unlink(missing_ok=True)
    return True


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def gateway_env(backend: str, token: str, dns_name: str, port: int) -> dict[str, str]:
    return {
        **os.environ,
        "DLCR_BACKENDS": f"http://{backend}",
        "DLCR_ORIGINS": f"https://{dns_name},http://127.0.0.1:{port},http://localhost:{port}",
        "DLCR_GATEWAY_TOKEN": token,
        "PORT": str(port),
    }


def wait_ready(proc: subprocess.Popen[bytes], port: int, err_log: Path) -> None:
    for _ in range(40):
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    tail = ""
    if err_log.exists():
        tail = "\n".join(err_log.read_text(errors="replace").splitlines()[-15:])
    raise LauncherError(f"The gateway did not start on port {port}.\n{tail}")


def start_gateway(node: str, env: dict[str, str], port: int, foreground: bool) -> subprocess.Popen[bytes]:
    directory = state_dir()
    out_log, err_log = directory / "web-gateway.log", directory / "web-gateway.err.log"
    if not port_is_free(port):
        raise LauncherError(f"Port {port} is already in use by another program. Pass --port to use a different one.")
    command = [node, "server/gateway.mjs"]
    if foreground:
        proc = subprocess.Popen(command, cwd=WEB_ROOT, env=env)
        return proc
    kwargs: dict[str, Any] = {}
    if IS_WINDOWS:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    with open(out_log, "ab") as out, open(err_log, "ab") as err:
        proc = subprocess.Popen(command, cwd=WEB_ROOT, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, **kwargs)
    pid_file().write_text(str(proc.pid))
    wait_ready(proc, port, err_log)
    return proc


def start_serve(port: int) -> None:
    step("Publishing on your tailnet (tailscale serve)")
    exe = find_tool("tailscale", "Install Tailscale.")
    result = run([exe, "serve", "--bg", f"http://127.0.0.1:{port}"])
    if result.returncode != 0:
        raise LauncherError(
            f"tailscale serve failed:\n{(result.stdout + result.stderr).strip()}\n"
            "If it says Serve is not enabled, open the link it prints and enable it once."
        )


def stop_serve() -> None:
    exe = shutil.which("tailscale")
    if exe:
        run([exe, "serve", "--https=443", "off"])


# --------------------------------------------------------------------------- extras
def copy_to_clipboard(text: str) -> bool:
    for command in (["clip"], ["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(command[0]):
            try:
                subprocess.run(command, input=text.encode(), check=True, timeout=5)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


def install_autostart() -> None:
    script = startup_script_path()
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else python
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f'@echo off\r\nstart "" /min "{runner}" "{Path(__file__).resolve()}" --no-browser\r\n',
        encoding="utf-8",
    )
    say(f"Autostart enabled: {script}")


def remove_autostart() -> None:
    startup_script_path().unlink(missing_ok=True)
    say("Autostart removed.")


# --------------------------------------------------------------------------- main
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Deep Live Cam web controller on this PC.")
    parser.add_argument("--backend", help="Colab Tailscale IP or host[:port] (default: auto-detect an online 'colab*' peer)")
    parser.add_argument("--backend-port", type=int, default=7860, help="Colab API port when --backend has none (default 7860)")
    parser.add_argument("--port", type=int, default=8787, help="local gateway port, bound to 127.0.0.1 (default 8787)")
    parser.add_argument("--no-serve", action="store_true", help="do not run tailscale serve")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--rebuild", action="store_true", help="force a web app rebuild")
    parser.add_argument("--rotate-token", action="store_true", help="generate a new gateway token")
    parser.add_argument("--foreground", action="store_true", help="run the gateway in this window (Ctrl+C stops it)")
    parser.add_argument("--stop", action="store_true", help="stop the gateway and remove the Tailscale Serve entry")
    parser.add_argument("--status", action="store_true", help="show whether the gateway is running")
    parser.add_argument("--install-autostart", action="store_true", help="start automatically at Windows login")
    parser.add_argument("--remove-autostart", action="store_true", help="remove the Windows login entry")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.remove_autostart:
            remove_autostart()
            return 0
        if args.stop:
            stopped = stop_gateway()
            stop_serve()
            say("Stopped the gateway and removed the Tailscale Serve entry." if stopped else "The gateway was not running; Tailscale Serve entry removed.")
            return 0
        if args.status:
            pid = running_gateway()
            say(f"Gateway: {f'running (PID {pid}, port {args.port})' if pid else 'not running'}")
            exe = shutil.which("tailscale")
            if exe:
                say(run([exe, "serve", "status"]).stdout.strip())
            return 0

        node, npm = check_node()
        status = tailscale_status()
        dns_name = self_dns_name(status)
        backend = resolve_backend(status, args.backend, args.backend_port)
        update_web_app(npm, args.rebuild)
        token = load_or_create_token(state_dir(), args.rotate_token)
        if running_gateway():
            step("Restarting the gateway")
            stop_gateway()
        step(f"Starting the gateway on 127.0.0.1:{args.port}")
        proc = start_gateway(node, gateway_env(backend, token, dns_name, args.port), args.port, args.foreground)
        if not args.no_serve:
            start_serve(args.port)
        if args.install_autostart:
            install_autostart()

        say("")
        say(f"Web controller:  https://{dns_name}/")
        say(f"Access token:    {token}")
        say(f"Backend (Colab): {backend}")
        say(f"Logs:            {state_dir() / 'web-gateway.log'}")
        say("In Connection: leave the gateway URL blank, paste the token, and press Check connection.")
        say("Stop with:       python scripts/start_web_controller.py --stop")
        if copy_to_clipboard(token):
            say("(Token copied to the clipboard.)")
        if not args.no_browser:
            webbrowser.open(f"http://localhost:{args.port}/")
        if args.foreground:
            try:
                return proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                return 0
        return 0
    except LauncherError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"ERROR: command failed ({error.returncode}): {' '.join(map(str, error.cmd))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
