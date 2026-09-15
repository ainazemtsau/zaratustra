"""Trusted local-agent confirmation backend over the existing application dispatch."""

from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from typing import Literal

from zaratustra.core import AuthorizationPrompt, LocalAuthorization, authorize_local
from zaratustra.intake import (
    MaterialIntakeAuthorization,
    PreparedMaterialIntake,
    authorize_material_intake,
    preview_bytes,
)
from zaratustra.local import ConfirmationBackend, use_confirmation_backend
from zaratustra.process_change import (
    ProcessChangeDecision,
    ReviewedProcessChange,
    authorize_process_change,
    process_change_preview_bytes,
)
from zaratustra.process_creation import (
    PreparedActivation,
    ProcessActivationAuthorization,
    activation_preview_bytes,
    authorize_process_activation,
)

ElicitationDecision = Literal["approve", "reject", "decline"]
Elicit = Callable[[str, str, bool], ElicitationDecision]


class _CapturedText(io.StringIO):
    """Capture the existing text and byte-oriented CLI outputs without a second dispatch."""

    def __init__(self) -> None:
        super().__init__()
        self._buffer = io.BytesIO()

    @property
    def buffer(self) -> io.BytesIO:
        return self._buffer

    def output(self) -> str:
        return str(self.getvalue()) + self._buffer.getvalue().decode("utf-8", errors="replace")


class TrustedLocalChatBackend(ConfirmationBackend):
    """Mint fresh in-process authorization only after a host-owned form acceptance."""

    def __init__(self, call_id: str, elicit: Elicit) -> None:
        if not call_id:
            raise ValueError("Missing trusted tool call identity")
        self._call_id = call_id
        self._elicit = elicit

    def _decision(
        self, title: str, exact: str, *, allow_reject: bool = False
    ) -> Literal["approve", "reject"]:
        decision = self._elicit(title, exact, allow_reject)
        if decision == "decline":
            from zaratustra.core import MutationError

            raise MutationError(
                "permission_denied", "Trusted local agent permission was not granted"
            )
        if decision == "reject" and not allow_reject:
            raise MutationError(
                "permission_denied", "Trusted local agent permission was not granted"
            )
        assert decision in {"approve", "reject"}
        return decision

    def _source_ref(self, operation: str) -> str:
        return f"trusted-local-agent-mcp:{self._call_id}:{operation}"

    def confirm(self, prompt: AuthorizationPrompt) -> LocalAuthorization:
        self._decision(
            "Authorize this exact local Zaratustra operation", prompt.model_dump_json(indent=2)
        )
        return authorize_local(
            prompt,
            channel="local-chat",
            actor="trusted-local-agent-mcp",
            source_ref=self._source_ref("operation"),
        )

    def confirm_activation(self, prepared: PreparedActivation) -> ProcessActivationAuthorization:
        self._decision(
            "Authorize this exact Zaratustra Process activation",
            activation_preview_bytes(prepared).decode("utf-8"),
        )
        return authorize_process_activation(
            prepared,
            channel="local-chat",
            actor="trusted-local-agent-mcp",
            source_ref=self._source_ref("activation"),
        )

    def confirm_change(self, review: ReviewedProcessChange) -> ProcessChangeDecision:
        decision = self._decision(
            "Decide this exact Zaratustra Process change",
            process_change_preview_bytes(review).decode("utf-8"),
            allow_reject=True,
        )
        return authorize_process_change(
            review,
            decision=decision,
            channel="local-chat",
            actor="trusted-local-agent-mcp",
            source_ref=self._source_ref("change"),
        )

    def confirm_material(self, prepared: PreparedMaterialIntake) -> MaterialIntakeAuthorization:
        self._decision(
            "Authorize this exact Zaratustra material intake",
            preview_bytes(prepared).decode("utf-8"),
        )
        return authorize_material_intake(
            prepared,
            channel="local-chat",
            actor="trusted-local-agent-mcp",
            source_ref=self._source_ref("material"),
        )


def run(argv: list[str], *, call_id: str, elicit: Elicit) -> tuple[int, str, str]:
    """Run the installed CLI application once with the supplied trusted local backend."""
    if not argv or not all(isinstance(value, str) and value for value in argv):
        raise ValueError("Command arguments must be a non-empty list of non-empty strings")
    # Local import keeps CLI's ordinary console path independent of this optional host adapter.
    from zaratustra.cli import main

    stdout = _CapturedText()
    stderr = _CapturedText()
    backend = TrustedLocalChatBackend(call_id, elicit)
    with use_confirmation_backend(backend), redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.output(), stderr.output()


__all__ = ["Elicit", "ElicitationDecision", "TrustedLocalChatBackend", "run"]
