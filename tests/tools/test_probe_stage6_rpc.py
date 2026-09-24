"""Isolated Stage 6 probe children return exact non-ASCII JSON through a pipe.

On Windows a piped child otherwise writes the ANSI code page, and ``-I`` ignores
PYTHONIOENCODING. A Linux C/POSIX locale already implies UTF-8 mode, so there this
check cannot tell a missing flag apart; the Windows gate can.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tools import probe_install_stage6, probe_stage6_rpc

# Cyrillic code points keep the child command line ASCII-only.
CODES = (0x421, 0x432, 0x435, 0x434, 0x435, 0x43D, 0x438, 0x44F)


@pytest.mark.parametrize(
    "flags", [probe_stage6_rpc.ISOLATED_UTF8, probe_install_stage6.ISOLATED_UTF8]
)
def test_isolated_child_prints_exact_non_ascii_json(flags: tuple[str, ...]) -> None:
    child = (
        "import json; "
        f"print(json.dumps({{'text': ''.join(map(chr, {CODES!r}))}}, ensure_ascii=False))"
    )
    result = subprocess.run(
        [sys.executable, *flags, "-c", child],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "-I" in flags
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"text": "".join(map(chr, CODES))}
