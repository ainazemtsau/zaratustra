# Fixed SQLite process bootstrap

This development-only directory is placed on child-process `PYTHONPATH` by
`tools.check` only when `ZARATUSTRA_SQLITE_DLL` is explicitly set. `sitecustomize`
must load and verify exactly the same official SQLite 3.53.3 DLL admitted by
`zaratustra.foundation.runtime` before pytest or another tool can import stdlib
`sqlite3`. It grants no product authority and must not search for or download a DLL.

END_OF_FILE: tools/sqlite_bootstrap/AGENTS.md

