"""Explicit console confirmation under the owner's accepted local trust boundary."""

import hashlib
import json
import os
import sys
from typing import TextIO
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


__all__ = ["confirm_material_intake_on_console", "confirm_on_console"]
