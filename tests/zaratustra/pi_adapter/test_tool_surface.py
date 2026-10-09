"""Keep the interactive Pi tool menu aligned with the extension it loads."""

from __future__ import annotations

import re
from importlib.resources import files

from zaratustra.foundation import ALL_ACTIONS
from zaratustra.pi_adapter.__main__ import INTERACTIVE_ZARA_TOOLS


def test_every_registered_zara_tool_is_enabled_in_interactive_pi() -> None:
    extension = files("zaratustra.pi_adapter").joinpath("extension.ts").read_text(encoding="utf-8")
    registered = {
        block.split('name: "', 1)[1].split('"', 1)[0]
        for block in extension.split("pi.registerTool({")[1:]
        if 'name: "' in block and block.split('name: "', 1)[1].startswith("zara_")
    }

    assert registered == set(INTERACTIVE_ZARA_TOOLS)
    assert len(INTERACTIVE_ZARA_TOOLS) == len(registered)
    assert "zara_activity" in registered
    assert "zara_sleep" in registered


def test_grant_tool_actions_match_core_actions() -> None:
    extension = files("zaratustra.pi_adapter").joinpath("extension.ts").read_text(encoding="utf-8")
    grant = extension.split('name: "zara_grant"', 1)[1].split('name: "zara_sleep"', 1)[0]
    actions = grant.split("actions: Type.Array(StringEnum([", 1)[1].split("] as const)", 1)[0]

    assert set(re.findall(r'"([a-z]+[.][a-z]+)"', actions)) == set(ALL_ACTIONS)
