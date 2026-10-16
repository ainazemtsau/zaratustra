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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
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
        received.append({"pinned": pinned["body"]["value"], "actual": asdict(executor.live)})
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
    selected[field] = value
    profile.write_text(json.dumps(selected), encoding="utf-8")
    with pytest.raises(CoreError, match="profile.configuration"):
        cli.main()
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
