from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .store import StoreError


def normalize_formats(formats: Iterable[str] | None, *, allowed: set[str], default: list[str], label: str = "report") -> list[str]:
    requested: list[str] = []
    for value in formats or default:
        for item in str(value).split(","):
            normalized = item.strip().lower()
            if normalized:
                requested.append(normalized)
    invalid = sorted(set(requested) - allowed)
    if invalid:
        allowed_text = ", ".join(sorted(allowed))
        raise StoreError(f"Unknown {label} format(s): {', '.join(invalid)}. Use {allowed_text}.", exit_code=2)
    return requested or list(default)


def run_pandoc(input_path: Path, output_path: Path, *, extra_args: list[str], label: str = "report") -> None:
    if shutil.which("pandoc") is None:
        raise StoreError(f"pandoc is required for HTML/PDF {label}s. Install pandoc or request --format md.", exit_code=2)
    command = ["pandoc", str(input_path), "-o", str(output_path), *extra_args]
    result = subprocess.run(command, cwd=input_path.parent, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise StoreError(f"pandoc failed writing {output_path.name}: {detail}", exit_code=1)


def rel_path(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve()).replace(os.sep, "/")


def md_link(label: str, path: Path, output_dir: Path) -> str:
    return f"[{esc_md(label)}]({rel_path(path, output_dir)})"


def esc_md(value: str) -> str:
    return value.replace("|", "\\|")
