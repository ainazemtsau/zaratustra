"""Explicit console confirmation under the owner's accepted local trust boundary."""

import hashlib
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal, Protocol, TextIO
from uuid import uuid4

from zaratustra.core import (
    AuthorizationPrompt,
    LocalAuthorization,
    MutationError,
    authorize_local,
)
from zaratustra.intake import (
    MaterialIntakeAuthorization,
    PreparedMaterialIntake,
    authorize_material_intake,
    preview_bytes,
)
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


class ConfirmationBackend(Protocol):
    """A host-owned local confirmation surface; authority objects stay in-process."""

    def confirm(self, prompt: AuthorizationPrompt) -> LocalAuthorization: ...

    def confirm_activation(
        self, prepared: PreparedActivation
    ) -> ProcessActivationAuthorization: ...

    def confirm_change(self, review: ReviewedProcessChange) -> ProcessChangeDecision: ...

    def confirm_material(self, prepared: PreparedMaterialIntake) -> MaterialIntakeAuthorization: ...


_backend: ContextVar[ConfirmationBackend | None] = ContextVar(
    "zaratustra_confirmation_backend", default=None
)


@contextmanager
def use_confirmation_backend(backend: ConfirmationBackend) -> Iterator[None]:
    """Inject one trusted local host confirmation backend for this application call."""
    token = _backend.set(backend)
    try:
        yield
    finally:
        _backend.reset(token)


def _confirm(
    prompt: AuthorizationPrompt, input_stream: TextIO, output_stream: TextIO
) -> LocalAuthorization:
    if not input_stream.isatty() or not output_stream.isatty():
        raise MutationError("permission_denied", "Interactive local console confirmation required")
    # Escaped JSON prevents operation strings from injecting terminal controls.
    print(
        json.dumps(prompt.model_dump(mode="json"), ensure_ascii=True, indent=2), file=output_stream
    )
    print("Authorize only this displayed internal operation/query.", file=output_stream)
    print(f"Type approve {prompt.request_sha256}", file=output_stream, flush=True)
    answer = input_stream.readline().strip()
    if answer != f"approve {prompt.request_sha256}":
        raise MutationError("permission_denied", "Operation was not confirmed")
    return authorize_local(
        prompt,
        channel="local-console",
        actor="local-console-operator",
        source_ref=f"console-confirmation:{uuid4()}",
    )


def confirm_on_console(
    prompt: AuthorizationPrompt, *, separate_terminal: bool = False
) -> LocalAuthorization:
    selected = _backend.get()
    if selected is not None:
        return selected.confirm(prompt)
    if not separate_terminal:
        return _confirm(prompt, sys.stdin, sys.stderr)
    # The pipe is data only. Obtain confirmation from the controlling console.
    input_name, output_name = ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
    try:
        with (
            open(input_name, encoding="utf-8") as terminal_input,
            open(output_name, "w", encoding="utf-8") as terminal_output,
        ):
            return _confirm(prompt, terminal_input, terminal_output)
    except OSError as error:
        raise MutationError("permission_denied", "Controlling local console unavailable") from error


def confirm_process_activation_on_console(
    prepared: PreparedActivation,
) -> ProcessActivationAuthorization:
    """Confirm the complete activation preview once at the trusted local console."""
    selected = _backend.get()
    if selected is not None:
        return selected.confirm_activation(prepared)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise MutationError("permission_denied", "Interactive local console confirmation required")
    content = activation_preview_bytes(prepared)
    digest = hashlib.sha256(content).hexdigest()
    print(content.decode("utf-8").rstrip(), file=sys.stderr)
    print(
        "Activate only this displayed process proposal and missing operation suffix.",
        file=sys.stderr,
    )
    print(f"Type activate {digest}", file=sys.stderr, flush=True)
    if sys.stdin.readline().strip() != f"activate {digest}":
        raise MutationError("permission_denied", "Process activation was not confirmed")
    return authorize_process_activation(
        prepared,
        channel="local-console",
        actor="local-console-operator",
        source_ref=f"console-process-activation:{uuid4()}",
    )


def confirm_process_change_on_console(
    review: ReviewedProcessChange,
) -> ProcessChangeDecision:
    """Show and bind one explicit approve/reject decision to the exact change preview."""
    selected = _backend.get()
    if selected is not None:
        return selected.confirm_change(review)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise MutationError("permission_denied", "Interactive local console confirmation required")
    content = process_change_preview_bytes(review)
    digest = hashlib.sha256(content).hexdigest()
    if digest != review.preview_sha256:
        raise MutationError("permission_denied", "Changed process change preview")
    print(content.decode("utf-8").rstrip(), file=sys.stderr)
    print("Decide only this displayed future-edition change.", file=sys.stderr)
    print(f"Type approve {digest} or reject {digest}", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip()
    if answer == f"approve {digest}":
        decision: Literal["approve", "reject"] = "approve"
    elif answer == f"reject {digest}":
        decision = "reject"
    else:
        raise MutationError("permission_denied", "Process change was not decided")
    return authorize_process_change(
        review,
        decision=decision,
        channel="local-console",
        actor="local-console-operator",
        source_ref=f"console-process-change:{uuid4()}",
    )


def _confirm_material_intake(
    prepared: PreparedMaterialIntake, input_stream: TextIO, output_stream: TextIO
) -> MaterialIntakeAuthorization:
    if not input_stream.isatty() or not output_stream.isatty():
        raise MutationError("permission_denied", "Interactive local console confirmation required")
    digest = hashlib.sha256(preview_bytes(prepared)).hexdigest()
    if digest != prepared.preview_sha256:
        raise MutationError("permission_denied", "Changed intake preview")
    print(
        json.dumps(prepared.preview.model_dump(mode="json"), ensure_ascii=True, indent=2),
        file=output_stream,
    )
    print(
        "Authorize only this displayed receipt/publication/acceptance plan; "
        "Work completion is not requested.",
        file=output_stream,
    )
    print(f"Type approve {digest}", file=output_stream, flush=True)
    if input_stream.readline().strip() != f"approve {digest}":
        raise MutationError("permission_denied", "Incoming material was not confirmed")
    return authorize_material_intake(
        prepared,
        channel="local-console",
        actor="local-console-operator",
        source_ref=f"console-intake-confirmation:{uuid4()}",
    )


def confirm_material_intake_on_console(
    prepared: PreparedMaterialIntake, *, separate_terminal: bool = False
) -> MaterialIntakeAuthorization:
    selected = _backend.get()
    if selected is not None:
        return selected.confirm_material(prepared)
    if not separate_terminal:
        return _confirm_material_intake(prepared, sys.stdin, sys.stderr)
    input_name, output_name = ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
    try:
        with (
            open(input_name, encoding="utf-8") as terminal_input,
            open(output_name, "w", encoding="utf-8") as terminal_output,
        ):
            return _confirm_material_intake(prepared, terminal_input, terminal_output)
    except OSError as error:
        raise MutationError("permission_denied", "Controlling local console unavailable") from error


__all__ = [
    "confirm_material_intake_on_console",
    "confirm_on_console",
    "confirm_process_change_on_console",
    "confirm_process_activation_on_console",
    "ConfirmationBackend",
    "use_confirmation_backend",
]
