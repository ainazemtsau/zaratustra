"""Public Core surface for the admitted workspace foundation."""

from .mutations import (
    AuthorizationPrompt,
    LocalAuthorization,
    MutationError,
    apply_mutation,
    authorize_local,
    prepare_authorization,
    read_history,
    read_receipt,
    read_records,
)
from .protocol import MutationEvent, MutationHistory, MutationReceipt, MutationRequest, ReceiptQuery
from .records import (
    Artifact,
    Event,
    InitialRecords,
    Process,
    RecordsSnapshot,
    Work,
    create_initial_records,
)
from .workspace import (
    WorkspaceError,
    WorkspaceInfo,
    init_workspace,
    migrate_workspace,
    read_workspace,
)

__all__ = [
    "AuthorizationPrompt",
    "LocalAuthorization",
    "MutationError",
    "MutationEvent",
    "MutationHistory",
    "MutationReceipt",
    "MutationRequest",
    "ReceiptQuery",
    "apply_mutation",
    "authorize_local",
    "prepare_authorization",
    "read_history",
    "read_receipt",
    "Artifact",
    "Event",
    "InitialRecords",
    "Process",
    "RecordsSnapshot",
    "Work",
    "WorkspaceError",
    "WorkspaceInfo",
    "create_initial_records",
    "init_workspace",
    "migrate_workspace",
    "read_records",
    "read_workspace",
]
