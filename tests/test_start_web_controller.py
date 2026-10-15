"""Unit tests for scripts/start_web_controller.py (no Node, Tailscale or network needed)."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "start_web_controller.py"
spec = importlib.util.spec_from_file_location("start_web_controller", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
sys.modules["start_web_controller"] = launcher
spec.loader.exec_module(launcher)

STATUS = {
    "BackendState": "Running",
    "Self": {"DNSName": "dje-pc.tail091bc7.ts.net."},
    "Peer": {
        "a": {"HostName": "colab-dlc-remote-1", "Online": False, "TailscaleIPs": ["100.115.69.11"], "Created": "2026-10-10T00:00:00Z"},
        "b": {"HostName": "colab-dlc-remote-2", "Online": True, "TailscaleIPs": ["fd7a::1", "100.110.24.125"], "Created": "2026-10-14T00:00:00Z"},
        "c": {"HostName": "colab-dlc-remote-3", "Online": True, "TailscaleIPs": ["100.99.0.3"], "Created": "2026-10-12T00:00:00Z"},
        "d": {"HostName": "iphone-13", "Online": True, "TailscaleIPs": ["100.102.222.124"], "Created": "2026-10-15T00:00:00Z"},
    },
}


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("DLCR_STATE_DIR", str(tmp_path / "state"))


def test_parse_node_version_and_minimum():
    assert launcher.parse_node_version("v22.12.0\n") == (22, 12)
    assert launcher.parse_node_version("24.1.3") == (24, 1)
    assert launcher.parse_node_version("v22.11.0") < launcher.MIN_NODE
    with pytest.raises(launcher.LauncherError):
        launcher.parse_node_version("not node")


def test_self_dns_name_strips_trailing_dot_and_requires_magicdns():
    assert launcher.self_dns_name(STATUS) == "dje-pc.tail091bc7.ts.net"
    with pytest.raises(launcher.LauncherError):
        launcher.self_dns_name({"Self": {}})


def test_pick_colab_backend_uses_newest_online_colab_ipv4():
    target, names = launcher.pick_colab_backend(STATUS, 7860)
    assert target == "100.110.24.125:7860"
    assert names == ["colab-dlc-remote-2", "colab-dlc-remote-3"]


def test_pick_colab_backend_without_online_colab_explains_next_step():
    offline = {"Peer": {"a": {"HostName": "colab-x", "Online": False}, "b": {"HostName": "pc", "Online": True}}}
    with pytest.raises(launcher.LauncherError, match="--backend"):
        launcher.pick_colab_backend(offline, 7860)
    with pytest.raises(launcher.LauncherError):
        launcher.pick_colab_backend({"Peer": None}, 7860)


@pytest.mark.parametrize("given, expected", [
    ("100.1.2.3", "100.1.2.3:7860"),
    ("100.1.2.3:9000", "100.1.2.3:9000"),
    ("http://100.1.2.3:7860/", "100.1.2.3:7860"),
    ("colab-x.ts.net", "colab-x.ts.net:7860"),
])
def test_resolve_backend_explicit_forms(given, expected):
    assert launcher.resolve_backend(STATUS, given, 7860) == expected


def test_needs_install_and_build_follow_file_times(tmp_path):
    web = tmp_path / "web"
    (web / "src").mkdir(parents=True)
    (web / "node_modules").mkdir()
    (web / "dist").mkdir()
    lock, marker = web / "package-lock.json", web / "node_modules" / ".package-lock.json"
    source, dist = web / "src" / "main.tsx", web / "dist" / "index.html"
    for file in (lock, marker, source, dist):
        file.write_text("x")
    base = 1_000_000
    os.utime(lock, (base, base))
    os.utime(marker, (base + 10, base + 10))
    os.utime(source, (base, base))
    os.utime(dist, (base + 10, base + 10))
    assert not launcher.needs_install(web)
    assert not launcher.needs_build(web)
    assert launcher.needs_build(web, force=True)
    os.utime(lock, (base + 20, base + 20))
    assert launcher.needs_install(web)
    os.utime(source, (base + 30, base + 30))
    assert launcher.needs_build(web)
    dist.unlink()
    assert launcher.needs_build(web)
    marker.unlink()
    assert launcher.needs_install(web)


def test_token_is_created_kept_and_rotated(tmp_path):
    first = launcher.load_or_create_token(tmp_path, rotate=False)
    assert len(first) >= 24
    assert launcher.load_or_create_token(tmp_path, rotate=False) == first
    assert launcher.load_or_create_token(tmp_path, rotate=True) != first


def test_unreadable_or_short_token_is_replaced(tmp_path):
    (tmp_path / "web-gateway.token").write_text("garbage")
    assert len(launcher.load_or_create_token(tmp_path, rotate=False)) >= 24
    (tmp_path / "web-gateway.token").write_text("plain:short")
    assert len(launcher.load_or_create_token(tmp_path, rotate=False)) >= 24


def test_gateway_env_allows_only_expected_origins_and_backend():
    env = launcher.gateway_env("100.110.24.125:7860", "t" * 30, "dje-pc.tail091bc7.ts.net", 8787)
    assert env["DLCR_BACKENDS"] == "http://100.110.24.125:7860"
    assert env["DLCR_ORIGINS"].split(",") == [
        "https://dje-pc.tail091bc7.ts.net", "http://127.0.0.1:8787", "http://localhost:8787"]
    assert env["PORT"] == "8787"
    assert env["DLCR_GATEWAY_TOKEN"] == "t" * 30


def test_stale_pid_file_is_cleared_and_never_stops_an_unrelated_process():
    launcher.pid_file().write_text(str(os.getpid()))  # a live process that is not the gateway
    assert launcher.running_gateway() is None
    assert not launcher.pid_file().exists()
    assert launcher.stop_gateway() is False
    launcher.pid_file().write_text("not a pid")
    assert launcher.running_gateway() is None


def test_port_is_free_detects_a_listener():
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert not launcher.port_is_free(port)
    assert launcher.port_is_free(port)


def test_autostart_is_windows_only(monkeypatch):
    monkeypatch.setattr(launcher, "IS_WINDOWS", False)
    with pytest.raises(launcher.LauncherError):
        launcher.startup_script_path()


def test_argument_defaults():
    args = launcher.parse_args([])
    assert (args.port, args.backend_port, args.backend) == (8787, 7860, None)
    assert launcher.parse_args(["--stop", "--port", "9000"]).port == 9000
