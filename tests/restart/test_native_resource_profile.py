"""Native subscription resource choice is explicit; no credential access for admission."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from zaratustra_app import LiveProfile
from zaratustra_core import CoreError

from .support import METHOD, fixture, inspect


@pytest.mark.parametrize("mode", [None, "token-limit", "money-limit", True, 8, {}])
def test_native_resource_mode_must_be_explicit(tmp_path: Path, mode: Any) -> None:
    with pytest.raises(CoreError, match="unsupported_capability"):
        LiveProfile(
            endpoint="https://api.openai.com/v1",
            model="gpt-6-luna",
            auth_mode="pi-chatgpt",
            auth_path=str(tmp_path / "nonexistent-auth.json"),
            native_resource_mode=mode,
        )
    assert not list(tmp_path.iterdir())


def test_native_calls_only_identity_is_retained_without_auth_read(tmp_path: Path) -> None:
    profile = LiveProfile(
        endpoint="https://api.openai.com/v1",
        model="gpt-6-luna",
        auth_mode="pi-chatgpt",
        auth_path=str(tmp_path / "nonexistent-auth.json"),
        native_resource_mode="calls-only",
        max_tokens=64,
    )
    assert asdict(profile)["native_resource_mode"] == "calls-only"
    assert profile.configuration()["native_resource_mode"] == "calls-only"
    assert profile.max_tokens == 64 and not list(tmp_path.iterdir())


def test_api_key_profile_retains_requested_output_configuration() -> None:
    profile = LiveProfile(
        endpoint="https://provider.invalid/v1",
        model="selected-model",
        credential_env="FICTIONAL_SELECTED_KEY",
        max_tokens=64,
    )
    assert profile.max_tokens == 64 and profile.native_resource_mode is None
    assert "native_resource_mode" not in profile.configuration()
    with pytest.raises(CoreError, match="live_profile.native_resource_mode"):
        LiveProfile(
            endpoint=profile.endpoint,
            model=profile.model,
            credential_env=profile.credential_env,
            native_resource_mode="calls-only",
        )


@pytest.mark.parametrize("limit", [{"token_limit": 64}, {"money_limit": "1.00"}])
def test_core_noncall_resource_demand_remains_unsupported(
    tmp_path: Path, limit: dict[str, Any]
) -> None:
    core, owner, _ = fixture(tmp_path)
    assert owner.call("describe_contract", {}, "contract")["resource_units"] == ["calls"]
    before = inspect(core, "works")
    with pytest.raises(CoreError, match="unsupported_capability"):
        owner.call(
            "open_work",
            {
                "id": "unsupported-work",
                "conversation": "conversation",
                "goal": "fictional bounded demand",
                "method_ref": METHOD,
                "call_limit": 8,
                "continuation_policy": "durable",
            }
            | limit,
            "unsupported-demand",
        )
    assert inspect(core, "works") == before and inspect(core, "actions") == []
