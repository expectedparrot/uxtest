from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .store import Store, StoreError, atomic_write_yaml, read_json, read_yaml, slugify, validate_name


DRIVERS = {"edsl", "heuristic", "scripted"}
DEVICES = {"desktop", "iphone", "pixel"}


def fixture_dir(store: Store, name: str) -> Path:
    validate_name(name, "fixture name")
    return store.fixtures_path / name


def fixture_path(store: Store, name: str) -> Path:
    path = fixture_dir(store, name) / "fixture.yaml"
    if not path.is_file():
        raise StoreError(f"Fixture {name!r} does not exist.", exit_code=2)
    return path


def list_fixtures(store: Store) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    if not store.fixtures_path.exists():
        return fixtures
    for child in sorted(store.fixtures_path.iterdir()):
        path = child / "fixture.yaml"
        if child.is_dir() and path.is_file():
            data = read_yaml(path)
            fixtures.append(
                {
                    "id": str(data.get("id") or child.name),
                    "name": str(data.get("name") or data.get("id") or child.name),
                    "path": str(path),
                    "variants": [str(item.get("name")) for item in data.get("variants", []) if isinstance(item, dict)],
                }
            )
    return fixtures


def create_fixture(
    store: Store,
    name: str,
    *,
    source: Path | None = None,
    url_template: str | None = None,
    task: str | None = None,
    success_criteria: str | None = None,
    personas: list[str] | None = None,
    variants: list[str] | None = None,
    driver: str | None = None,
    device: str | None = None,
    force: bool = False,
) -> Path:
    validate_name(name, "fixture name")
    destination = fixture_dir(store, name)
    if destination.exists() and not force:
        raise StoreError(f"Fixture {name!r} already exists; use --force to replace it.", exit_code=2)
    if source is not None:
        data = load_fixture_source(source)
    else:
        data = {}
    data["id"] = name
    data.setdefault("name", name.replace("-", " ").title())
    data.setdefault("comparison_title", f"{data['name']} Comparison")
    data.setdefault("comparison_output", f"{name}.html")
    if url_template is not None:
        data["url_template"] = url_template
    if task is not None:
        data["task"] = task
    if success_criteria is not None:
        data["success_criteria"] = success_criteria
    if personas:
        data["personas"] = personas
    data.setdefault("personas", ["seniors"])
    if driver is not None:
        data["driver"] = driver
    data.setdefault("driver", "edsl")
    if device is not None:
        data["device"] = device
    data.setdefault("device", "desktop")
    data.setdefault("runs_per_persona", 1)
    data.setdefault("max_steps", 8)
    data.setdefault("max_concurrent_runs", 1)
    if variants:
        data["variants"] = [{"name": item} for item in variants]
    data.setdefault("variants", [{"name": "default"}])
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    output = destination / "fixture.yaml"
    atomic_write_yaml(output, data)
    return output


def register_fixture(
    store: Store,
    source: Path,
    *,
    name: str | None = None,
    plan: str | None = None,
    force: bool = False,
) -> Path:
    source = source.expanduser().resolve()
    source_file = _source_file(source, plan=plan)
    data = load_fixture_source(source_file)
    fixture_name = name or str(data.get("id") or slugify(source.stem if source.is_file() else source.name))
    validate_name(fixture_name, "fixture name")
    destination = fixture_dir(store, fixture_name)
    if source.is_dir() and destination.is_relative_to(source):
        raise StoreError(
            "Cannot register a directory into a store inside that same directory; run `uxtest init` in its parent first.",
            exit_code=2,
        )
    if destination.exists() and not force:
        raise StoreError(f"Fixture {fixture_name!r} already exists; use --force to replace it.", exit_code=2)
    if destination.exists():
        shutil.rmtree(destination)
    if source.is_dir():
        shutil.copytree(source, destination)
        copied_source = destination / source_file.relative_to(source)
    else:
        destination.mkdir(parents=True)
        copied_source = destination / source_file.name
        shutil.copy2(source_file, copied_source)
    data["id"] = fixture_name
    output = destination / "fixture.yaml"
    atomic_write_yaml(output, data)
    if copied_source != output and copied_source.exists():
        copied_source.unlink()
    return output


def load_fixture_source(source: Path) -> dict[str, Any]:
    if str(source) == "-":
        try:
            data = json.load(sys.stdin)
        except (json.JSONDecodeError, OSError) as exc:
            raise StoreError(f"Invalid fixture JSON on stdin: {exc}", exit_code=2) from exc
        if not isinstance(data, dict):
            raise StoreError("Fixture JSON must be an object.", exit_code=2)
        return data
    source = source.expanduser().resolve()
    if not source.is_file():
        raise StoreError(f"Fixture source does not exist: {source}", exit_code=2)
    if source.suffix.lower() == ".json":
        return read_json(source)
    return read_yaml(source)


def validate_fixture(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fixture_id = data.get("id")
    if not isinstance(fixture_id, str) or not fixture_id:
        errors.append("id must be a non-empty string")
    else:
        try:
            validate_name(fixture_id, "fixture id")
        except StoreError as exc:
            errors.append(str(exc))
    if not isinstance(data.get("task"), str) or not data.get("task", "").strip():
        errors.append("task must be a non-empty string")
    variants = data.get("variants")
    if not isinstance(variants, list) or not variants:
        errors.append("variants must be a non-empty list")
        variants = []
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict) or not isinstance(variant.get("name"), str) or not variant.get("name"):
            errors.append(f"variants[{index}] must be an object with a non-empty name")
    if not data.get("url_template") and not all(isinstance(item, dict) and item.get("url") for item in variants):
        errors.append("url_template is required unless every variant defines url")
    personas = data.get("personas", ["seniors"])
    if not isinstance(personas, list) or not personas or not all(isinstance(item, str) and item for item in personas):
        errors.append("personas must be a non-empty list of names")
    driver = data.get("driver", "edsl")
    if driver not in DRIVERS:
        errors.append(f"driver must be one of: {', '.join(sorted(DRIVERS))}")
    device = data.get("device", "desktop")
    if device not in DEVICES:
        errors.append(f"device must be one of: {', '.join(sorted(DEVICES))}")
    for field in ("runs_per_persona", "max_steps", "max_concurrent_runs"):
        value = data.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            errors.append(f"{field} must be a positive integer")
    return errors


def set_fixture_value(store: Store, name: str, key: str, raw_value: str, *, json_value: bool = False) -> Path:
    path = fixture_path(store, name)
    data = read_yaml(path)
    if json_value:
        try:
            value: Any = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise StoreError(f"Invalid JSON value: {exc}", exit_code=2) from exc
    else:
        value = _coerce_value(raw_value)
    target = data
    parts = key.split(".")
    if any(not part for part in parts):
        raise StoreError("Fixture key must be dot-separated non-empty names.", exit_code=2)
    for part in parts[:-1]:
        existing = target.get(part)
        if existing is None:
            existing = {}
            target[part] = existing
        if not isinstance(existing, dict):
            raise StoreError(f"Cannot set {key!r}; {part!r} is not an object.", exit_code=2)
        target = existing
    target[parts[-1]] = value
    atomic_write_yaml(path, data)
    return path


def add_persona(store: Store, name: str, persona: str) -> Path:
    validate_name(persona, "persona name")
    path = fixture_path(store, name)
    data = read_yaml(path)
    personas = data.setdefault("personas", [])
    if not isinstance(personas, list):
        raise StoreError("Fixture personas is not a list.", exit_code=2)
    if persona not in personas:
        personas.append(persona)
    atomic_write_yaml(path, data)
    return path


def add_variant(store: Store, name: str, variant: str, *, url: str | None, driver: str | None, device: str | None) -> Path:
    validate_name(variant, "variant name")
    path = fixture_path(store, name)
    data = read_yaml(path)
    variants = data.setdefault("variants", [])
    if not isinstance(variants, list):
        raise StoreError("Fixture variants is not a list.", exit_code=2)
    if any(isinstance(item, dict) and item.get("name") == variant for item in variants):
        raise StoreError(f"Variant {variant!r} already exists in fixture {name!r}.", exit_code=2)
    spec: dict[str, Any] = {"name": variant}
    if url:
        spec["url"] = url
    if driver:
        spec["driver"] = driver
    if device:
        spec["device"] = device
    variants.append(spec)
    atomic_write_yaml(path, data)
    return path


def _source_file(source: Path, *, plan: str | None = None) -> Path:
    if source.is_file():
        if plan:
            raise StoreError("--plan can only be used when registering a directory.", exit_code=2)
        return source
    if not source.is_dir():
        raise StoreError(f"Fixture source does not exist: {source}", exit_code=2)
    if plan:
        candidate = (source / plan).resolve()
        if not candidate.is_relative_to(source) or not candidate.is_file():
            raise StoreError(f"Fixture plan does not exist inside {source}: {plan}", exit_code=2)
        return candidate
    candidates = [
        source / "fixture.yaml",
        source / "fixture.yml",
        source / "fixture.json",
        source / "regression.yaml",
        source / "regression.yml",
        source / "regression.json",
    ]
    candidates.extend(sorted(source.glob("*.yaml")))
    candidates.extend(sorted(source.glob("*.yml")))
    candidates.extend(sorted(source.glob("*.json")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise StoreError(f"No fixture YAML or JSON found in {source}.", exit_code=2)


def _coerce_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value
