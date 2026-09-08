"""Retain a stopped fictional trial, including empty directories, in a new ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def retain_trial(trial: Path, target: Path) -> dict[str, object]:
    """Copy selected trial bytes and layout; never overwrite an earlier archive."""
    trial = trial.resolve(strict=True)
    target = target.resolve()
    if not trial.is_dir() or target.is_relative_to(trial):
        raise ValueError("Choose a trial directory and an archive outside it.")
    files: dict[str, str] = {}
    directories: list[str] = []
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as archive:
        for parent, dirs, names in trial.walk():
            dirs[:] = sorted(name for name in dirs if name not in {"venv", "__pycache__"})
            for name in [*dirs, *sorted(names)]:
                path = parent / name
                if path.is_symlink() or path.is_junction():
                    raise ValueError(f"Trial entry must not be a link: {path}")
                relative = path.relative_to(trial).as_posix()
                if path.is_dir():
                    directories.append(relative + "/")
                    archive.writestr(relative + "/", b"")
                else:
                    data = path.read_bytes()
                    files[relative] = hashlib.sha256(data).hexdigest()
                    archive.writestr(relative, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Retained archive failed CRC verification.")
        actual_files = {
            item.filename: hashlib.sha256(archive.read(item)).hexdigest()
            for item in archive.infolist()
            if not item.is_dir()
        }
        actual_dirs = sorted(item.filename for item in archive.infolist() if item.is_dir())
        if actual_files != files or actual_dirs != sorted(directories):
            raise ValueError("Retained archive differs from the selected bytes or layout.")
    return {
        "trial": str(trial),
        "archive": str(target),
        "archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "files": files,
        "directories": sorted(directories),
        "excluded_directories": ["venv", "__pycache__"],
        "method": "ZIP CRC, every decompressed file SHA-256 and complete directory inventory",
        "restore": (
            "Extract into a NEW folder; install retained wheel and locked requirements separately. "
            "Do not use fault-workspace as a base. Historical absolute paths remain provenance."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(retain_trial(args.trial, args.archive), indent=2))


if __name__ == "__main__":
    main()
