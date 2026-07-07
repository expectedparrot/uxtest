from __future__ import annotations

import datetime as dt
import contextlib
import json
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml


STORE_DIRNAME = "uxtest_store"
NAME_RE = re.compile(r"^[a-z0-9._-]+$")
SLUG_RE = re.compile(r"[^a-z0-9]+")


class StoreError(RuntimeError):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_id_prefix() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def slugify(value: str, max_len: int = 40) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "study")[:max_len].strip("-") or "study"


def validate_name(name: str, kind: str = "name") -> None:
    if not NAME_RE.match(name):
        raise StoreError(f"Invalid {kind} {name!r}; use only [a-z0-9._-].", exit_code=2)


def find_store(start: Path | str | None = None, override: Path | str | None = None) -> "Store":
    if override is None:
        override = os.environ.get("UXTEST_DIR")
    if override:
        path = Path(override).expanduser().resolve()
        if path.name != STORE_DIRNAME:
            path = path / STORE_DIRNAME
        if not path.is_dir():
            raise StoreError(f"No uxtest store found at {path}.", exit_code=3)
        return Store(path)

    current = Path(start or os.getcwd()).resolve()
    for directory in (current, *current.parents):
        for candidate in (directory / STORE_DIRNAME, directory / "data" / STORE_DIRNAME):
            if candidate.is_dir():
                return Store(candidate)
    raise StoreError("No uxtest store found. Run `uxtest init` first.", exit_code=3)


def default_new_store_root(base: Path | str | None = None) -> Path:
    """Directory to create a brand-new store in when none is discovered.

    When `base` contains a `data/` directory, the store nests inside it, so a
    fresh store lands at `data/uxtest_store`; otherwise it is created directly
    under `base` (the cwd). `find_store` checks both locations while walking up,
    so wherever a project is driven from, the same store is found.
    """
    base_path = Path(base or os.getcwd()).resolve()
    data_dir = base_path / "data"
    return data_dir if data_dir.is_dir() else base_path


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    # Directory fsync is a POSIX-only durability step; O_DIRECTORY is absent on
    # Windows, so skip it there rather than raising AttributeError.
    o_directory = getattr(os, "O_DIRECTORY", None)
    if o_directory is not None:
        try:
            dir_fd = os.open(str(path.parent), o_directory)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))


def atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    atomic_write_text(path, text)


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise StoreError(f"Expected YAML mapping in {path}.")
    return data


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise StoreError(f"Expected JSON object in {path}.")
    return data


@dataclass(frozen=True)
class Store:
    path: Path

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def config_path(self) -> Path:
        return self.path / "config.yaml"

    @property
    def personas_path(self) -> Path:
        return self.path / "personas"

    @property
    def studies_path(self) -> Path:
        return self.path / "studies"

    @property
    def locks_path(self) -> Path:
        return self.path / "locks"

    @property
    def cache_path(self) -> Path:
        return self.path / "cache"

    @classmethod
    def init(
        cls,
        root: Path | str,
        *,
        force: bool = False,
        project_name: str | None = None,
        base_url: str = "http://127.0.0.1:8765/?variant=confusing",
    ) -> "Store":
        root_path = Path(root).resolve()
        store_path = root_path / STORE_DIRNAME
        if store_path.exists() and not force:
            raise StoreError(f"{store_path} already exists; use --force to refresh defaults.", exit_code=2)

        store = cls(store_path)
        store.personas_path.mkdir(parents=True, exist_ok=True)
        store.studies_path.mkdir(parents=True, exist_ok=True)
        store.cache_path.mkdir(parents=True, exist_ok=True)
        store.locks_path.mkdir(parents=True, exist_ok=True)

        if force or not store.config_path.exists():
            atomic_write_yaml(store.config_path, default_config(project_name or root_path.name, base_url))

        example_persona = store.personas_path / "seniors.yaml"
        if not example_persona.exists():
            atomic_write_yaml(example_persona, default_persona("seniors"))

        gitignore = store.path / ".gitignore"
        if not gitignore.exists():
            atomic_write_text(gitignore, DEFAULT_STORE_GITIGNORE)

        return store

    def ensure(self) -> None:
        if not self.path.is_dir():
            raise StoreError(f"No uxtest store found at {self.path}.", exit_code=3)

    def create_persona(self, name: str, description: str | None = None) -> Path:
        validate_name(name, "persona name")
        path = self.personas_path / f"{name}.yaml"
        if path.exists():
            raise StoreError(f"Persona {name!r} already exists.", exit_code=2)
        atomic_write_yaml(path, default_persona(name, description=description))
        return path

    def write_persona(self, persona: dict[str, Any]) -> Path:
        name = persona.get("name")
        if not isinstance(name, str):
            raise StoreError("Persona is missing string name.", exit_code=2)
        validate_name(name, "persona name")
        path = self.personas_path / f"{name}.yaml"
        atomic_write_yaml(path, persona)
        return path

    def create_study(
        self,
        title: str,
        *,
        task: str,
        url: str,
        success_criteria: str = "",
        personas: list[str] | None = None,
        runs_per_persona: int | None = None,
        tags: list[str] | None = None,
    ) -> Path:
        if not task.strip():
            raise StoreError("--task is required.", exit_code=2)
        if not url.strip():
            raise StoreError("--url is required.", exit_code=2)
        personas = personas or ["seniors"]
        for persona in personas:
            validate_name(persona, "persona name")
            if not (self.personas_path / f"{persona}.yaml").exists():
                raise StoreError(f"Persona {persona!r} does not exist.", exit_code=2)

        study_id = self._next_study_id(title)
        study_dir = self.studies_path / study_id
        study_dir.mkdir(parents=True, exist_ok=False)
        (study_dir / "runs").mkdir()
        (study_dir / "analysis").mkdir()
        data: dict[str, Any] = {
            "schema_version": 1,
            "id": study_id,
            "title": title,
            "created_at": utc_now(),
            "status": "draft",
            "task": task,
            "url": url,
            "success_criteria": success_criteria,
            "personas": personas,
            "tags": tags or [],
        }
        if runs_per_persona is not None:
            data["runs_per_persona"] = runs_per_persona
        atomic_write_yaml(study_dir / "study.yaml", data)
        return study_dir

    def list_studies(self) -> list[dict[str, Any]]:
        studies: list[dict[str, Any]] = []
        if not self.studies_path.exists():
            return studies
        for child in sorted(self.studies_path.iterdir()):
            if not child.is_dir():
                continue
            study_file = child / "study.yaml"
            if study_file.exists():
                study = read_yaml(study_file)
                study["_path"] = str(study_file)
                studies.append(study)
        return studies

    def load_config(self) -> dict[str, Any]:
        return read_yaml(self.config_path)

    def study_dir(self, study_id: str) -> Path:
        validate_name(study_id, "study id")
        path = self.studies_path / study_id
        if not path.is_dir():
            raise StoreError(f"Study {study_id!r} does not exist.", exit_code=2)
        return path

    def load_study(self, study_id: str) -> dict[str, Any]:
        return read_yaml(self.study_dir(study_id) / "study.yaml")

    def load_persona(self, name: str) -> dict[str, Any]:
        validate_name(name, "persona name")
        path = self.personas_path / f"{name}.yaml"
        if not path.exists():
            raise StoreError(f"Persona {name!r} does not exist.", exit_code=2)
        return read_yaml(path)

    def write_study(self, study: dict[str, Any]) -> None:
        study_id = study.get("id")
        if not isinstance(study_id, str):
            raise StoreError("Study is missing string id.")
        atomic_write_yaml(self.study_dir(study_id) / "study.yaml", study)

    def set_study_status(self, study_id: str, status: str) -> None:
        study = self.load_study(study_id)
        study["status"] = status
        self.write_study(study)

    def next_run_id(self, study_id: str, persona_name: str) -> str:
        validate_name(persona_name, "persona name")
        runs_path = self.study_dir(study_id) / "runs"
        existing = [child.name for child in runs_path.iterdir() if child.is_dir()]
        max_sequence = 0
        for name in existing:
            match = re.match(r"run-(\d+)-", name)
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))
        return f"run-{max_sequence + 1:03d}-{persona_name}-{uuid4().hex[:4]}"

    def lock_path(self, study_id: str) -> Path:
        validate_name(study_id, "study id")
        return self.locks_path / f"{study_id}.lock"

    @contextlib.contextmanager
    def study_lock(self, study_id: str, *, break_stale: bool = True):
        lock_path = self.lock_path(study_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": utc_now(),
            "study_id": study_id,
        }
        acquired = False
        try:
            while True:
                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(payload, handle, indent=2, sort_keys=True)
                        handle.write("\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    acquired = True
                    break
                except FileExistsError:
                    if break_stale and self._lock_is_stale(lock_path):
                        lock_path.unlink(missing_ok=True)
                        continue
                    raise StoreError(f"Study {study_id!r} is locked by {lock_path}.", exit_code=4)
            yield
        finally:
            if acquired:
                lock_path.unlink(missing_ok=True)

    def _lock_is_stale(self, lock_path: Path) -> bool:
        try:
            data = read_json(lock_path)
        except Exception:
            return False
        if data.get("hostname") != socket.gethostname():
            return False
        pid = data.get("pid")
        if not isinstance(pid, int):
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def list_runs(self, study_id: str) -> list[Path]:
        runs_path = self.study_dir(study_id) / "runs"
        if not runs_path.exists():
            return []
        return sorted(child for child in runs_path.iterdir() if child.is_dir())

    def load_run_meta(self, study_id: str, run_id: str) -> dict[str, Any]:
        validate_name(run_id, "run id")
        meta_path = self.study_dir(study_id) / "runs" / run_id / "meta.json"
        if not meta_path.exists():
            raise StoreError(f"Run {run_id!r} has no meta.json.", exit_code=2)
        return read_json(meta_path)

    def recover_stale_runs(self, study_id: str) -> int:
        if self.lock_path(study_id).exists():
            return 0
        recovered = 0
        for run_dir in self.list_runs(study_id):
            meta_path = run_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = read_json(meta_path)
            except Exception:
                continue
            if meta.get("outcome") is not None:
                continue
            meta["finished_at"] = utc_now()
            meta["outcome"] = "interrupted"
            meta["outcome_detail"] = "Recovered stale run with no live study lock."
            meta["steps_taken"] = count_jsonl_lines(run_dir / "trace.jsonl")
            atomic_write_json(meta_path, meta)
            recovered += 1
        return recovered

    def status(self) -> dict[str, Any]:
        studies = self.list_studies()
        runs = 0
        incomplete_runs = 0
        for study in studies:
            study_id = study.get("id")
            if not isinstance(study_id, str):
                continue
            self.recover_stale_runs(study_id)
            run_dir = self.studies_path / study_id / "runs"
            if not run_dir.exists():
                continue
            for child in run_dir.iterdir():
                if not child.is_dir():
                    continue
                runs += 1
                meta = child / "meta.json"
                if not meta.exists():
                    incomplete_runs += 1
                    continue
                try:
                    data = read_json(meta)
                except Exception:
                    incomplete_runs += 1
                    continue
                if data.get("outcome") is None:
                    incomplete_runs += 1
        return {
            "store": str(self.path),
            "hostname": socket.gethostname(),
            "studies": len(studies),
            "runs": runs,
            "incomplete_runs": incomplete_runs,
        }

    def _next_study_id(self, title: str) -> str:
        base = f"{today_id_prefix()}-{slugify(title)}"
        candidate = base
        suffix = 2
        while (self.studies_path / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        validate_name(candidate, "study id")
        return candidate


def count_jsonl_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


DEFAULT_STORE_GITIGNORE = """# Derived and bulky data - keep out of git
studies/*/runs/
studies/*/analysis/report.html
studies/*/analysis/log.html
cache/
locks/
gc.log
"""


def default_config(project_name: str, base_url: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_name": slugify(project_name),
        "base_url": base_url,
        "defaults": {
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_steps": 30,
            "viewport": {"width": 1280, "height": 800},
            "screenshot": "full",
            "screenshot_format": "png",
            "screenshot_quality": 80,
            "a11y_audit": True,
            "runs_per_persona": 1,
        },
        "browser": {
            "engine": "chromium",
            "headless": True,
            "slow_mo_ms": 0,
        },
        "secrets": {
            "env_file": "secrets.env",
            "redact_patterns": [],
        },
    }


def default_persona(name: str, description: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "description": description or "Desktop shopper with moderate web familiarity",
        "attributes": {
            "age_range": [35, 55],
            "tech_literacy": "medium",
            "reading_style": "skims",
            "patience": "medium",
            "device_familiarity": "desktop",
        },
        "accessibility": {},
        "goals_bias": "Prefers clear labels, predictable checkout steps, and helpful error messages.",
        "frustration": {
            "threshold": 7,
            "per_step_decay": 1,
        },
    }
