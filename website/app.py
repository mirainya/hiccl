"""hiccl.dev — The official Hiccl website, built with Hiccl itself.

Usage:
    cd website
    uv run python app.py
    # Open http://127.0.0.1:8000

This is a self-hosting demonstration: the Hiccl web framework serves its own
landing page using its reactive component architecture, Hiccup DSL, and
built-in DaisyUI + TailwindCSS styling.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from hiccl import ComponentRegistry, HicclConfig, create_hiccl_app
from hiccl.app import _generate_font_tags

from .i18n import detect_lang
from .landing import LandingPage


# ── SEO meta tags ────────────────────────────────────────────────────

XCLOAK_CSS = "<style>[x-cloak] { display: none !important; }</style>"

SEO_META = """
  <meta name="description" content="Hiccl — A modern full-stack reactive web framework combining Clojure's Hiccup DSL with Pythonic state serialization. Pure Python, zero build, air-gapped ready.">
  <meta name="keywords" content="hiccl,python,web framework,full-stack,reactive,hiccup,clojure,fastapi,signal,datalog,csp,htmx,tailwindcss,daisyui,alpinejs">
  <meta property="og:title" content="Hiccl — Full-Stack Reactive Python Web Framework">
  <meta property="og:description" content="Clojure's Declarative Gene Meets Pythonic Full-Stack Reactivity. Pure Python, zero build.">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://hiccl.dev">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Hiccl — Full-Stack Reactive Python Web Framework">
  <meta name="twitter:description" content="Clojure's Declarative Gene Meets Pythonic Full-Stack Reactivity.">
"""

# ── Custom layout ────────────────────────────────────────────────────


def website_layout(
    request: Request, comp_html: str, menu_html: str, config: HicclConfig
) -> str:
    """Custom full-width layout for the landing page.

    Detects browser language from Accept-Language header to set <html lang>.
    Does NOT wrap content in navbar or card containers.
    """
    # Detect language from request headers
    accept_lang = request.headers.get("accept-language", "")
    html_lang = detect_lang(accept_lang)

    session_id = getattr(
        request.state, "hiccl_session_id", None
    ) or request.cookies.get(config.session_cookie_name, "")

    fonts_html = _generate_font_tags(config)

    return f"""<!DOCTYPE html>
<html lang="{html_lang}" data-theme="{config.theme}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{config.title}</title>
  <meta name="hiccl-session" content="{session_id}">
{SEO_META}
  <link href="/static/daisyui.css" rel="stylesheet" type="text/css" />
  <script src="/static/tailwind.js"></script>
  <script defer src="/static/alpine.js"></script>
  <script src="/static/htmx.js"></script>
  <script src="/static/hiccl.js"></script>
  {fonts_html}
  {config.head_extra}
</head>
<body class="min-h-screen bg-base-100">
  {comp_html}
</body>
</html>"""


# ── App factory ──────────────────────────────────────────────────────


def create_website_app() -> FastAPI:
    """Create the Hiccl-powered website application."""
    registry = ComponentRegistry()
    registry.register("landing-page", LandingPage)

    config = HicclConfig(
        component_registry=registry,
        # Route "/" → LandingPage
        pages={"/": LandingPage},
        # Custom full-width layout (no navbar, no card wrapper)
        layout=website_layout,
        show_navbar=False,
        # Branding
        title="Hiccl — Full-Stack Reactive Python Web Framework",
        brand_name="Hiccl",
        description=(
            "A modern full-stack reactive web framework combining "
            "Clojure's Hiccup DSL with Pythonic state serialization."
        ),
        # Dark theme with emerald accent
        theme="dark",
        # Offline mode: use local fonts (no Google Fonts CDN)
        offline_mode=True,
        # Inject x-cloak CSS for Alpine.js language switching
        head_extra=XCLOAK_CSS,
        # Static files from Hiccl's built-in static/ directory
        static_dir=None,  # We'll mount manually to cascade paths
    )

    app = create_hiccl_app(config)

    # Mount Hiccl's built-in static files (CSS/JS from framework)
    import os

    hiccl_static_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "hiccl", "static"
    )
    if os.path.isdir(hiccl_static_dir):
        app.mount("/static", StaticFiles(directory=hiccl_static_dir), name="static")

    return app


# ── Main entry point ─────────────────────────────────────────────────

app = create_website_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "website.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )
