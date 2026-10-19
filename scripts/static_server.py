"""Frontend-only mock server with explicit /js and /fixtures mounts."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = urlsplit(path).path
        if clean.startswith("/js/"):
            target = ROOT / "frontend" / clean.lstrip("/")
        elif clean.startswith("/fixtures/demo/"):
            target = ROOT / clean.lstrip("/")
        elif clean in {"/account-menu.js", "/rubric-library.js"}:
            target = ROOT / "frontend" / "js" / clean.lstrip("/")
        else:
            target = ROOT / "frontend" / "pages" / (clean.lstrip("/") or "00-home.html")
        return str(target.resolve())


if __name__ == "__main__":
    print("mock frontend: http://127.0.0.1:4173/00-home.html?mocks=1")
    ThreadingHTTPServer(("127.0.0.1", 4173), Handler).serve_forever()
