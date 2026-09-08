"""Explicit console confirmation under the owner's accepted local trust boundary."""

import sys
from uuid import uuid4

from zaratustra.core import (
    AuthorizationPrompt,
    LocalAuthorization,
    MutationError,
    authorize_local,
)


def confirm_on_console(prompt: AuthorizationPrompt) -> LocalAuthorization:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise MutationError("permission_denied", "Interactive local console confirmation required")
    # Escaped JSON prevents operation strings from injecting terminal controls.
    import json

    print(json.dumps(prompt.model_dump(mode="json"), ensure_ascii=True, indent=2), file=sys.stderr)
    print("Authorize only this displayed internal operation/query.", file=sys.stderr)
    print(f"Type approve {prompt.request_sha256}", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip()
    if answer != f"approve {prompt.request_sha256}":
        raise MutationError("permission_denied", "Operation was not confirmed")
    return authorize_local(
        prompt,
        channel="local-console",
        actor="local-console-operator",
        source_ref=f"console-confirmation:{uuid4()}",
    )


__all__ = ["confirm_on_console"]
