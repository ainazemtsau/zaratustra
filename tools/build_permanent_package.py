"""Build a local, hash-pinned portable Pi package without publishing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("zaratustra-core", "zaratustra-next")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_packages(lock: dict[str, Any]) -> list[dict[str, Any]]:
    """Take the full dependency closure, including platform-conditional edges."""
    packages = {package["name"]: package for package in lock["package"]}
    pending = list(PRODUCTS)
    included: set[str] = set()
    while pending:
        name = pending.pop()
        if name in included:
            continue
        included.add(name)
        pending.extend(dependency["name"] for dependency in packages[name].get("dependencies", []))
    return [packages[name] for name in sorted(included)]


def build(output: Path, source_dist: Path | None = None) -> Path:
    if output.exists():
        raise ValueError("Output must be a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zaratustra-package-", dir=output.parent) as temporary:
        staging = Path(temporary)
        dist = source_dist or staging / "dist"
        if source_dist is None:
            for package_name in ("core", "app"):
                subprocess.run(
                    [
                        "uv",
                        "build",
                        "--wheel",
                        "--out-dir",
                        str(dist),
                        str(ROOT / "packages" / package_name),
                    ],
                    check=True,
                )
        package_root = staging / "package"
        shutil.copytree(ROOT / "pi-package", package_root, ignore=shutil.ignore_patterns("wheels"))
        wheels = package_root / "wheels"
        wheels.mkdir()
        lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
        requirements = []
        versions = {}
        for package in runtime_packages(lock):
            name, version = package["name"], package["version"]
            if name in PRODUCTS:
                candidates = list(
                    dist.glob(name.replace("-", "_") + f"-{version}-py3-none-any.whl")
                )
                if len(candidates) != 1:
                    raise ValueError(f"Missing exact universal product wheel: {name}=={version}")
                wheel = candidates[0]
                shutil.copyfile(wheel, wheels / wheel.name)
                hashes = ["sha256:" + sha256(wheel)]
                versions[name] = version
            else:
                hashes = sorted({artifact["hash"] for artifact in package.get("wheels", [])})
                if not hashes:
                    raise ValueError(f"No locked wheels for {name}")
                # Optional locally supplied dependencies allow native offline checks.
                allowed = set(hashes)
                for wheel in dist.glob(name.replace("-", "_") + f"-{version}-*.whl"):
                    if "sha256:" + sha256(wheel) not in allowed:
                        raise ValueError(f"Unrecognized dependency wheel: {wheel.name}")
                    shutil.copyfile(wheel, wheels / wheel.name)
            requirements.append(
                name + "==" + version + " " + " ".join("--hash=" + h for h in hashes)
            )
        requirement_file = package_root / "requirements.txt"
        requirement_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        (package_root / "release.json").write_text(
            json.dumps(
                {
                    "versions": versions,
                    "requirements_sha256": sha256(requirement_file),
                    "core_required_protocol": 1,
                    "supported_read_protocols": [0, 1],
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest = "".join(
            f"{sha256(wheel)}  {wheel.name}\n" for wheel in sorted(wheels.glob("*.whl"))
        )
        (wheels / "SHA256SUMS").write_text(manifest, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package_root, output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "--output-folder", "--outputfolder", required=True, type=Path)
    parser.add_argument("--source-dist", type=Path)
    args = parser.parse_args()
    print(build(args.output.resolve(), args.source_dist))


if __name__ == "__main__":
    main()
