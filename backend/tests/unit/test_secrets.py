from subprocess import CompletedProcess
from unittest.mock import patch

from app.security.secrets import protect_secret, unprotect_secret


def test_macos_keychain_secret_round_trip_commands() -> None:
    stored = CompletedProcess([], 0, stdout="", stderr="")
    loaded = CompletedProcess([], 0, stdout="secret-value\n", stderr="")
    with patch("app.security.secrets.sys.platform", "darwin"), patch(
        "app.security.secrets.subprocess.run", side_effect=[stored, loaded]
    ) as run:
        reference = protect_secret("secret-value")
        assert reference == "keychain:ai-assisted-marker:local-ai-api-key"
        assert unprotect_secret(reference) == "secret-value"

    assert run.call_count == 2
    assert run.call_args_list[0].args[0][0] == "security"
    assert run.call_args_list[1].args[0][1] == "find-generic-password"
