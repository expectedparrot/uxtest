from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .store import Store, StoreError, read_json


def prune_study_runs(store: Store, study_id: str, *, keep: int, dry_run: bool = False) -> list[Path]:
    if keep < 1:
        raise StoreError("--keep must be at least 1.", exit_code=2)
    runs = _sorted_runs(store, study_id)
    to_delete = runs[:-keep]
    if dry_run:
        return to_delete
    for run_dir in to_delete:
        shutil.rmtree(run_dir)
    return to_delete


def _sorted_runs(store: Store, study_id: str) -> list[Path]:
    return sorted(store.list_runs(study_id), key=_run_sort_key)


def _run_sort_key(run_dir: Path) -> tuple[str, str]:
    meta_path = run_dir / "meta.json"
    started_at = ""
    if meta_path.exists():
        try:
            meta: dict[str, Any] = read_json(meta_path)
            started_at = str(meta.get("started_at") or "")
        except Exception:
            started_at = ""
    return (started_at, run_dir.name)
