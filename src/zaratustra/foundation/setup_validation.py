"""Typed diagnostics for a new model result, never for stored-state corruption."""

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from .capabilities import ProcedureOperation
from .models import SetupValidationIssue
from .storage import FoundationError


class SetupResultError(FoundationError):
    def __init__(self, code: str, detail: str, path: tuple[str | int, ...] = ()) -> None:
        super().__init__(code, detail)
        self.issues: tuple[SetupValidationIssue, ...] = (
            SetupValidationIssue(code=code, path=path, message=detail[:2048]),
        )


def validation_issues(error: ValidationError) -> tuple[SetupValidationIssue, ...]:
    issues = []
    for item in error.errors(include_input=False, include_context=False, include_url=False)[:16]:
        path = tuple(item["loc"])
        operation_error = "operations" in path
        issues.append(
            SetupValidationIssue(
                code="unsupported_operation" if operation_error else str(item["type"]),
                path=path,
                message=(
                    "Use an exact operation name from supported_operations; describe steps in prose"
                    if operation_error
                    else str(item["msg"])[:2048]
                ),
                allowed_values=tuple(ProcedureOperation) if operation_error else (),
            )
        )
    return tuple(issues)


def validate_new_value[T](
    path: tuple[str | int, ...], function: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Call only pure validators of the new response, with no stored-state access."""
    try:
        return function(*args, **kwargs)
    except ValidationError as error:
        issues = validation_issues(error)
        converted = SetupResultError("invalid_setup_result", "Invalid response value", path)
        converted.issues = tuple(
            issue.model_copy(update={"path": path + issue.path}) for issue in issues
        )
        raise converted from error
    except FoundationError as error:
        raise SetupResultError(error.code, error.detail, path) from error
