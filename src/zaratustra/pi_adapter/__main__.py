"""Launch one ordinary interactive Pi with an epoch-bound local Core bridge."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import threading
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from zaratustra.foundation import (
    BootstrapRequest,
    LocalAuthority,
    apply_operation,
    authorize_local,
    initialize_space,
    inspect_space,
    managed_pi_session_lock,
    managed_pi_sessions,
    read_space,
    upgrade_execution_space,
    upgrade_space,
)

from .bridge import Bridge, BridgeServer


def _prepare_space(path: Path, actor: str, *, create: bool) -> LocalAuthority:
    if create:
        initialize_space(path)
    info = read_space(path)
    authority = authorize_local(path, actor=actor, source_ref=f"local-console:{actor}:{uuid4()}")
    if info.state_revision == 0:
        apply_operation(
            path,
            BootstrapRequest(
                operation_id=uuid4(),
                space_id=info.space_id,
                actor=actor,
                decision_id=uuid4(),
                grant_id=uuid4(),
            ),
            authority,
        )
    if read_space(path).schema_version == 1:
        upgrade_space(path, authority)
    if read_space(path).schema_version == 2:
        upgrade_execution_space(path, authority)
    return authority


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pi-cli", required=True, type=Path)
    parser.add_argument(
        "--pi-runtime",
        required=True,
        type=Path,
        help="Directory with node_modules for the selected upstream Pi",
    )
    parser.add_argument("--node", default="node")
    parser.add_argument("--new-space", action="store_true")
    parser.add_argument("--limit-units", type=int, required=True)
    parser.add_argument("--reserve-units", type=int, required=True)
    parser.add_argument(
        "--provider-profile", choices=("codex-sse", "local-completions"), default="codex-sse"
    )
    parser.add_argument("--provider-base-url", help="Selected Pi Provider endpoint")
    parser.add_argument("--local-provider-id")
    parser.add_argument("--local-model-id")
    parser.add_argument("--local-context-window", type=int)
    parser.add_argument("--local-max-tokens", type=int)
    parser.add_argument("--model", help="Provider/model selected by Pi; no product default")
    parser.add_argument("--thinking", help="Pi reasoning level")
    parser.add_argument("--pi-tools", help="Optional comma-separated Pi tool allowlist")
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--activity-id", type=UUID)
    parser.add_argument("--work-id", type=UUID)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("Start from an interactive local console for trusted setup")
    space = args.space.expanduser().resolve()
    workspace = args.workspace.expanduser().resolve()
    pi_cli = args.pi_cli.expanduser().resolve()
    runtime = args.pi_runtime.expanduser().resolve()
    expected_sessions = space / ".zara-core" / "pi-sessions"
    if args.session_dir and args.session_dir.expanduser().resolve() != expected_sessions:
        parser.error(f"Pi sessions must use the managed Core directory: {expected_sessions}")
    if not workspace.is_dir() or not pi_cli.is_file() or not (runtime / "node_modules").is_dir():
        parser.error("Workspace, Pi CLI or Pi runtime is unavailable")
    if args.limit_units < 1 or args.reserve_units < 1:
        parser.error("Model resource limits must be positive")
    base_url = args.provider_base_url or (
        "https://chatgpt.com/backend-api" if args.provider_profile == "codex-sse" else None
    )
    if not base_url:
        parser.error("Local Provider needs an explicit base URL")
    parsed_url = urlsplit(base_url)
    if parsed_url.scheme not in ("https", "http") or not parsed_url.hostname:
        parser.error("Provider base URL must be an absolute HTTP URL")
    if args.provider_profile == "local-completions" and (
        not args.local_provider_id
        or not args.local_model_id
        or not args.local_context_window
        or not args.local_max_tokens
    ):
        parser.error("Local Provider needs id, model and context/output bounds")
    if (args.activity_id is None) != (args.work_id is None):
        parser.error("Initial Activity and Work must be selected together")
    actor = getpass.getuser()
    print(f"Core space: {space}\nWorking directory: {workspace}\nLocal user: {actor}")
    print(
        f"Provider profile: {args.provider_profile}\n"
        f"Pi model: {args.model or 'Pi selection'}\n"
        f"Pi tools: {args.pi_tools or 'none'}\n"
        f"Work limit: {args.limit_units} units; each call reserve: {args.reserve_units} units"
    )
    if args.activity_id:
        print(f"Activity: {args.activity_id}\nWork: {args.work_id}")
    if input("Type CONNECT to use these paths and local identity: ").strip() != "CONNECT":
        return 1
    authority = _prepare_space(space, actor, create=args.new_space)
    with managed_pi_session_lock(space):
        if inspect_space(space, authority).pending_deletions:
            parser.error("Complete pending Core deletions before opening Pi")
        session_dir = managed_pi_sessions(space, authority.space_id, create=True)
        bridge = Bridge(space, authority, workspace, args.limit_units)
        executor_store = space / ".zara-core" / "executor.sqlite3"
        if executor_store.is_file():
            from .assigned import deliver_outbox

            bridge.deliver_answer = lambda outbox_id: deliver_outbox(space, authority, outbox_id)
        server = BridgeServer(bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        extension = Path(str(files("zaratustra.pi_adapter").joinpath("extension.ts")))
        installed = runtime / "zaratustra-extension.ts"
        shutil.copy2(extension, installed)
        environment = os.environ.copy()
        environment["ZARA_CORE_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}"
        environment["ZARA_CORE_TOKEN"] = bridge.token
        environment["ZARA_RESERVE_UNITS"] = str(args.reserve_units)
        environment["ZARA_PROVIDER_PROFILE"] = args.provider_profile
        environment["ZARA_PROVIDER_BASE_URL"] = base_url
        environment["ZARA_PROVIDER_ORIGIN"] = f"{parsed_url.scheme}://{parsed_url.netloc}"
        if args.activity_id:
            environment["ZARA_INITIAL_ACTIVITY_ID"] = str(args.activity_id)
            environment["ZARA_INITIAL_WORK_ID"] = str(args.work_id)
        if args.provider_profile == "local-completions":
            environment["ZARA_LOCAL_PROVIDER_ID"] = args.local_provider_id
            environment["ZARA_LOCAL_MODEL_ID"] = args.local_model_id
            environment["ZARA_LOCAL_CONTEXT_WINDOW"] = str(args.local_context_window)
            environment["ZARA_LOCAL_MAX_TOKENS"] = str(args.local_max_tokens)
        command = [
            args.node,
            str(pi_cli),
            "--provider",
            "openai-codex" if args.provider_profile == "codex-sse" else args.local_provider_id,
            "--extension",
            str(installed),
            "--no-extensions",
            "--no-context-files",
        ]
        if args.model:
            command.extend(["--model", args.model])
        if args.thinking:
            command.extend(["--thinking", args.thinking])
        if args.pi_tools:
            command.extend(["--tools", args.pi_tools])
        else:
            command.append("--no-tools")
        command.extend(["--session-dir", str(session_dir)])
        try:
            return subprocess.run(command, cwd=workspace, env=environment, check=False).returncode
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            installed.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
