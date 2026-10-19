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
    for package in ("ingest", "extract", "retrieval", "grading", "report"):
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
