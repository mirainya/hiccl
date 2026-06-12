"""Integration smoke test for the hiccl.dev website.

Verifies that the Hiccl-powered landing page renders correctly with all
expected sections, bilingual content, SEO meta tags, and static assets.
"""

import os
import socket
import sys
import threading
import time
import urllib.request


_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "src"))
sys.path.insert(0, _project_root)
os.chdir(_project_root)

import uvicorn  # noqa: E402

from website.app import app  # noqa: E402


def _find_free_port() -> int:
    """Find a free port to use for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_website():
    port = _find_free_port()

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(3)

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            html = resp.read().decode("utf-8")

            checks = [
                ("DOCTYPE", "<!DOCTYPE html>"),
                ("html lang", 'lang="en"'),
                ("data-theme dark", 'data-theme="dark"'),
                ("title tag", "<title>Hiccl"),
                ("meta desc", 'name="description"'),
                ("meta og", "og:title"),
                ("meta twitter", "twitter:card"),
                ("daisyui css", "daisyui.css"),
                ("tailwind js", "tailwind.js"),
                ("alpine js", "alpine.js"),
                ("htmx js", "htmx.js"),
                ("hiccl js", "hiccl.js"),
                ("x-cloak", "x-cloak"),
                ("section features", 'id="features"'),
                ("section stack", 'id="stack"'),
                ("section quickstart", 'id="quickstart"'),
                ("section install", 'id="install"'),
                ("sticky navbar", "sticky top-0"),
                ("lang switcher", "switchLang"),
                ("GitHub link", "github.com/shiunko/hiccl"),
                ("counter code", "class Counter"),
                ("pip install", "pip install hiccl"),
                ("uv add", "uv add hiccl"),
                ("footer license", "MIT License"),
                ("zh content", "快速上手"),
                ("en content", "Quick Start"),
                ("features zh", "声明式 UI"),
                ("features en", "Declarative UI"),
                ("localStorage", "localStorage.getItem"),
                ("SVG icons", "<svg"),
                ("x-show directives", "x-show="),
            ]

            failed = []
            for label, text in checks:
                if text not in html:
                    failed.append(label)
                    print(f"  FAIL  {label}")
                else:
                    print(f"  ✓     {label}")

            assert not failed, f"Failed checks: {failed}"
            assert len(html) > 10000, f"HTML too short: {len(html)} bytes"
            assert html.count("x-show=") >= 50, (
                f"Too few x-show directives: {html.count('x-show=')}"
            )

            print(f"\n  All {len(checks)} checks passed!")
            print(f"  HTML size: {len(html)} bytes")
            print(f"  x-show directives: {html.count('x-show=')}")
            print("  ✓ Website is fully functional!")

    except Exception as e:
        print(f"\n  FAILED: {e}")
        raise


if __name__ == "__main__":
    test_website()
