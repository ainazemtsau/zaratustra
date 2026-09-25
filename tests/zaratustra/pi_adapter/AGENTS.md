# Pi adapter checks

Use only disposable synthetic Core spaces and localhost transport. Tests must
establish behavior from public APIs and never read credentials or contact models.
Keep tests for address-only Pi status and Attempt-specific DBOS routing; old
workflow addresses remain valid on repeated delivery.
