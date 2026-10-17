"""Public CLI refuses configuration drift before a different Pi profile can execute."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import LiveProfile, Sleep, cli
from zaratustra_core import Core, CoreError


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "model-b"),
        ("endpoint", "https://other.invalid/v1"),
        ("api", "openai-completions"),
        ("max_tokens", 4096),
        ("context_window", 65536),
        ("timeout", 90),
        ("credential_env", "OTHER_SELECTED_CREDENTIAL"),
        ("pi_cli", "other-pi.js"),
    ],
)
def test_cli_profile_drift_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: Any,
) -> None:
    core, token = Core.initialize(tmp_path / "space")
    (core.root / "owner.credential").write_text(token, encoding="utf-8")
    profile = tmp_path / "profile.json"
    selected = {
        "pi_cli": str(tmp_path / "pi.js"),
        "endpoint": "https://provider.invalid/v1",
        "model": "model-a",
        "credential_env": "SELECTED_CREDENTIAL",
    }
    received: list[dict[str, Any]] = []

    def execute(
        self: Sleep, work_id: str, profile_ref: dict[str, Any], executor: Any
    ) -> dict[str, Any]:
        pinned = self.client.call("read_exact", profile_ref, "capture-profile")
        actual = asdict(executor.live)
        if actual["native_resource_mode"] is None:
            del actual["native_resource_mode"]
        received.append({"pinned": pinned["body"]["value"], "actual": actual})
        return {"state": "ready"}

    monkeypatch.setattr(Sleep, "run", execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            "zaratustra-next",
            "--data-root",
            str(core.root),
            "sleep",
            "--work-id",
            "same-work",
            "--call-limit",
            "6",
            "--profile-file",
            str(profile),
        ],
    )
    profile.write_text(json.dumps(selected), encoding="utf-8")
    assert cli.main() == 0
    assert len(received) == 1
    assert all(received[0]["pinned"][key] == value for key, value in received[0]["actual"].items())
    capsys.readouterr()
    selected[field] = value
    profile.write_text(json.dumps(selected), encoding="utf-8")
    assert cli.main() == 1
    output = capsys.readouterr()
    error = json.loads(output.err)["error"]
    assert error["code"] == "stale_basis" and error["field"] == "profile.configuration"
    assert not output.out
    assert len(received) == 1
    snapshot = core.connect(token).call("read_snapshot", {}, "after-refusal")
    assert len(snapshot["works"]) == 1 and snapshot["actions"] == []


@pytest.mark.parametrize(
    "field,value",
    [("max_tokens", True), ("timeout", "90"), ("context_window", 0), ("max_tokens", 65536)],
)
def test_live_profile_resource_types_are_exact(field: str, value: Any) -> None:
    options = {"endpoint": "https://provider.invalid/v1", "model": "m", "credential_env": "KEY"}
    with pytest.raises(CoreError, match="live_profile"):
        LiveProfile(**(options | {field: value}))


def test_api_key_preexisting_profile_reopens_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, token = Core.initialize(tmp_path / "space")
    (core.root / "owner.credential").write_text(token, encoding="utf-8")
    profile_file = tmp_path / "api-profile.json"
    pi_cli = tmp_path / "unused-pi.js"
    old_descriptor = {
        "endpoint": "https://provider.invalid/v1",
        "model": "model-a",
        "credential_env": "SELECTED_CREDENTIAL",
        "api": "openai-responses",
        "max_tokens": 8192,
        "context_window": 32768,
        "timeout": 150,
        "auth_mode": "api-key",
        "auth_path": None,
        "pi_cli": str(pi_cli.resolve()),
        "resource_upper": 2,
    }
    profile_file.write_text(
        json.dumps(
            {
                "pi_cli": str(pi_cli),
                "endpoint": old_descriptor["endpoint"],
                "model": old_descriptor["model"],
                "credential_env": old_descriptor["credential_env"],
            }
        ),
        encoding="utf-8",
    )
    owner = core.connect(token)
    ref = {"id": "legacy-work:profile", "revision": 1}
    owner.call(
        "apply_changes",
        {
            "changes": [
                {"id": ref["id"], "kind": "profile", "key": ref["id"], "body": old_descriptor}
            ]
        },
        "prechange-profile",
        expected_heads={str(ref["id"]): 0},
    )
    before = owner.call("read_exact", ref, "before")
    executions: list[dict[str, Any]] = []

    def execute(
        self: Sleep, work_id: str, profile_ref: dict[str, Any], executor: Any
    ) -> dict[str, Any]:
        executions.append(self.client.call("read_exact", profile_ref, "during")["body"]["value"])
        return {"state": "ready"}

    monkeypatch.setattr(Sleep, "run", execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            "zaratustra-next",
            "--data-root",
            str(core.root),
            "sleep",
            "--work-id",
            "legacy-work",
            "--call-limit",
            "6",
            "--profile-file",
            str(profile_file),
        ],
    )
    assert cli.main() == 0 and cli.main() == 0
    assert executions == [old_descriptor, old_descriptor]
    assert owner.call("read_exact", ref, "after") == before
    snapshot = owner.call("read_snapshot", {}, "after-state")
    assert len(snapshot["works"]) == 1 and snapshot["actions"] == []
