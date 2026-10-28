import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend/app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_domain_has_no_infrastructure_dependencies() -> None:
    for path in (APP / "domain").glob("*.py"):
        forbidden = {
            name
            for name in imported_modules(path)
            if name.startswith("app.") and not name.startswith("app.domain")
        }
        assert not forbidden, f"{path.name}: {sorted(forbidden)}"


def test_processing_modules_do_not_import_api_or_database_models() -> None:
    for package in ("ingest", "extract", "retrieval", "grading", "report", "agent"):
        for path in (APP / package).rglob("*.py"):
            forbidden = {
                name
                for name in imported_modules(path)
                if name.startswith(("app.api", "app.db.models"))
            }
            assert not forbidden, f"{path.relative_to(APP)}: {sorted(forbidden)}"


def test_only_llm_package_imports_httpx() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        if (
            "httpx" in imported_modules(path)
            and "llm" not in path.relative_to(APP).parts
        ):
            offenders.append(str(path.relative_to(APP)))
    assert not offenders


def test_no_fixture_or_mock_data_paths_in_the_application() -> None:
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in ("FixtureStore", "fixtures_dir", "fixtures/demo", "is_mock", "use_mocks")):
            offenders.append(str(path.relative_to(APP)))
    assert not offenders


def test_jobs_do_not_import_the_http_layer() -> None:
    for path in (APP / "jobs").rglob("*.py"):
        forbidden = {name for name in imported_modules(path) if name.startswith("app.api")}
        assert not forbidden, f"{path.relative_to(APP)}: {sorted(forbidden)}"


def test_frontend_has_no_mock_mode() -> None:
    frontend = ROOT / "frontend"
    offenders = []
    for path in list(frontend.rglob("*.js")) + list(frontend.rglob("*.html")):
        if "pdfjs" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in ("mock-adapter", "mocks=1", "MarkerMockAdapter", "/fixtures/demo")):
            offenders.append(str(path.relative_to(frontend)))
    assert not offenders
