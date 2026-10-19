from pathlib import Path

import yaml

from app.main import app

ROOT = Path(__file__).resolve().parents[3]


def test_every_contract_operation_is_registered() -> None:
    contract = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    actual = app.openapi()["paths"]
    expected = {
        (path, method.upper())
        for path, value in contract["paths"].items()
        for method in value
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    registered = {
        (path, method.upper())
        for path, value in actual.items()
        for method in value
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    assert expected <= registered


def test_api_is_versioned() -> None:
    contract = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    assert all(path.startswith("/api/v1/") for path in contract["paths"])
