from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from .store import Store, StoreError, find_store


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except StoreError as exc:
        print(f"uxtest: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uxtest")
    parser.add_argument("--store", help="Path to .uxtest or its project root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a .uxtest store.")
    init.add_argument("--force", action="store_true")
    init.add_argument("--project-name")
    init.add_argument("--base-url", default="http://127.0.0.1:8765/?variant=confusing")
    init.set_defaults(func=cmd_init)

    persona = sub.add_parser("persona", help="Manage personas.")
    persona_sub = persona.add_subparsers(dest="persona_command", required=True)
    persona_new = persona_sub.add_parser("new", help="Create a persona template.")
    persona_new.add_argument("name")
    persona_new.add_argument("--description")
    persona_new.set_defaults(func=cmd_persona_new)

    study = sub.add_parser("study", help="Manage studies.")
    study_sub = study.add_subparsers(dest="study_command", required=True)
    study_new = study_sub.add_parser("new", help="Create a study.")
    study_new.add_argument("title")
    study_new.add_argument("--task", required=True)
    study_new.add_argument("--url", required=True)
    study_new.add_argument("--success-criteria", default="")
    study_new.add_argument("--persona", action="append", dest="personas")
    study_new.add_argument("--runs-per-persona", type=int)
    study_new.add_argument("--tag", action="append", dest="tags")
    study_new.set_defaults(func=cmd_study_new)

    study_list = study_sub.add_parser("list", help="List studies.")
    study_list.add_argument("--json", action="store_true")
    study_list.set_defaults(func=cmd_study_list)

    study_run = study_sub.add_parser("run", help="Run a study.")
    study_run.add_argument("id")
    study_run.add_argument("--persona")
    study_run.add_argument("--max-steps", type=int)
    study_run.add_argument("--max-concurrent-runs", type=int, default=1)
    study_run.add_argument("--continue-on-error", action="store_true")
    study_run.add_argument("--device", choices=["desktop", "iphone", "pixel"], help="Apply a built-in browser device profile for this run.")
    study_run.add_argument("--viewport", help="Viewport override as WIDTHxHEIGHT, for example 390x844.")
    study_run.add_argument("--mobile", action="store_true", help="Enable Playwright mobile mode for this run.")
    study_run.add_argument("--touch", action="store_true", help="Enable touch support for this run.")
    study_run.add_argument("--device-scale-factor", type=float)
    study_run.add_argument("--user-agent")
    study_run.add_argument(
        "--driver",
        choices=["edsl", "heuristic", "scripted"],
        default="edsl",
        help="Use EDSL model decisions, deterministic local heuristics, or a scripted fixture path.",
    )
    study_run.set_defaults(func=cmd_study_run)

    status = sub.add_parser("status", help="Show store status.")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    show = sub.add_parser("show", help="Show a study or run.")
    show.add_argument("id")
    show.add_argument("run_id", nargs="?")
    show.add_argument("--trace", action="store_true", help="Include trace events when showing a run.")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    analyze = sub.add_parser("analyze", help="Analyze a study and write analysis JSON.")
    analyze.add_argument("id")
    analyze.add_argument("--include-interrupted", action="store_true")
    analyze.add_argument("--driver", choices=["local", "edsl"], default="local")
    analyze.set_defaults(func=cmd_analyze)

    uxr = sub.add_parser("uxr", help="Generate UXR-facing study artifacts from analysis outputs.")
    uxr.add_argument("id")
    uxr.set_defaults(func=cmd_uxr)

    animate = sub.add_parser("animate", help="Generate per-run GIF animations from study screenshots.")
    animate.add_argument("id")
    animate.add_argument("--delay", type=int, default=250, help="Frame delay in centiseconds. 250 is 2.5 seconds.")
    animate.add_argument("--max-width", type=int, default=520)
    animate.add_argument("--open", action="store_true", help="Open the generated animation index.")
    animate.set_defaults(func=cmd_animate)

    eval_parser = sub.add_parser("eval", help="Evaluate recovered trace patterns against expected flaws.")
    eval_parser.add_argument("id")
    eval_parser.add_argument("--expect", type=Path, help="YAML file listing expected flaw ids.")
    eval_parser.add_argument("--variant", help="Variant name used to select expected_in/absent_in rules.")
    eval_parser.add_argument("--policy", choices=["strict", "threshold", "report_only"], default="strict")
    eval_parser.add_argument("--minimum-recovered-expected", type=int, default=1)
    eval_parser.add_argument("--open", action="store_true", help="Open the generated eval report.")
    eval_parser.set_defaults(func=cmd_eval)

    ci = sub.add_parser("ci", help="Run one or more fixture regression specs.")
    ci.add_argument("fixtures", nargs="+", type=Path, help="Fixture YAML file(s) to run.")
    ci.add_argument("--open", action="store_true", help="Open each generated comparison report.")
    ci.set_defaults(func=cmd_ci)

    prune = sub.add_parser("prune", help="Prune old run directories for a study.")
    prune.add_argument("id", help="Study id to prune.")
    prune.add_argument("--keep", type=int, required=True, help="Number of newest runs to keep.")
    prune.add_argument("--dry-run", action="store_true", help="Print runs that would be deleted without deleting them.")
    prune.set_defaults(func=cmd_prune)

    example = sub.add_parser("example", help="Example target utilities.")
    example_sub = example.add_subparsers(dest="example_command", required=True)
    serve = example_sub.add_parser("serve", help="Serve the checkout example.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_example_serve)
    example_run = example_sub.add_parser("run", help="Run the checkout example end to end.")
    example_run.add_argument("--host", default="127.0.0.1")
    example_run.add_argument("--port", type=int, default=8765)
    example_run.add_argument("--variant", choices=["confusing", "clear"], default="confusing")
    example_run.add_argument("--driver", choices=["edsl", "heuristic", "scripted"], default="edsl")
    example_run.add_argument("--max-steps", type=int, default=12)
    example_run.add_argument("--max-concurrent-runs", type=int, default=1)
    example_run.add_argument("--no-open", action="store_true", help="Do not open log.html after the run.")
    example_run.set_defaults(func=cmd_example_run)
    example_compare = example_sub.add_parser("compare", help="Run clear and confusing checkout variants and write a comparison report.")
    example_compare.add_argument("--host", default="127.0.0.1")
    example_compare.add_argument("--port", type=int, default=8765)
    example_compare.add_argument("--driver", choices=["edsl", "heuristic", "scripted"], default="heuristic")
    example_compare.add_argument("--max-steps", type=int, default=12)
    example_compare.add_argument("--max-concurrent-runs", type=int, default=2)
    example_compare.add_argument("--runs-per-persona", type=int, default=1)
    example_compare.add_argument(
        "--persona",
        action="append",
        dest="personas",
        help="Persona to include. Can be passed multiple times. Defaults to all example personas.",
    )
    example_compare.add_argument("--analysis-driver", choices=["local", "edsl"], default="local")
    example_compare.add_argument("--no-open", action="store_true", help="Do not open the comparison report after the run.")
    example_compare.set_defaults(func=cmd_example_compare)

    saas_serve = example_sub.add_parser("serve-saas", help="Serve the SaaS discovery example.")
    saas_serve.add_argument("--host", default="127.0.0.1")
    saas_serve.add_argument("--port", type=int, default=8776)
    saas_serve.set_defaults(func=cmd_example_serve_saas)

    saas_eval = example_sub.add_parser("eval-saas", help="Run the SaaS fixture regression harness.")
    saas_eval.add_argument("--host", default="127.0.0.1")
    saas_eval.add_argument("--port", type=int, default=8776)
    saas_eval.add_argument("--max-steps", type=int, default=6)
    saas_eval.add_argument("--delay", type=int, default=250, help="Animation frame delay in centiseconds.")
    saas_eval.add_argument("--no-open", action="store_true", help="Do not open the comparison report after the run.")
    saas_eval.set_defaults(func=cmd_example_eval_saas)

    return parser


def cmd_init(args: argparse.Namespace) -> None:
    store_root = Path(args.store).expanduser() if args.store else Path.cwd()
    if store_root.name == ".uxtest":
        store_root = store_root.parent
    store = Store.init(
        store_root,
        force=args.force,
        project_name=args.project_name,
        base_url=args.base_url,
    )
    print(f"Initialized {store.path}")


def cmd_persona_new(args: argparse.Namespace) -> None:
    store = find_store(override=args.store)
    path = store.create_persona(args.name, description=args.description)
    print(path.relative_to(store.root))


def cmd_study_new(args: argparse.Namespace) -> None:
    store = find_store(override=args.store)
    path = store.create_study(
        args.title,
        task=args.task,
        url=args.url,
        success_criteria=args.success_criteria,
        personas=args.personas,
        runs_per_persona=args.runs_per_persona,
        tags=args.tags,
    )
    print(path.relative_to(store.root))


def cmd_study_list(args: argparse.Namespace) -> None:
    store = find_store(override=args.store)
    studies = store.list_studies()
    if args.json:
        print(json.dumps(studies, indent=2, sort_keys=True))
        return
    if not studies:
        print("No studies.")
        return
    for study in studies:
        print(f"{study.get('id')}  {study.get('status', 'unknown')}  {study.get('title', '')}")


def cmd_study_run(args: argparse.Namespace) -> None:
    from .runner import run_study

    store = find_store(override=args.store)
    run_overrides = _run_overrides_from_args(args)
    run_dirs = run_study(
        store,
        args.id,
        persona_name=args.persona,
        max_steps=args.max_steps,
        driver=args.driver,
        max_concurrent_runs=args.max_concurrent_runs,
        continue_on_error=args.continue_on_error,
        run_overrides=run_overrides,
    )
    for run_dir in run_dirs:
        print(run_dir.relative_to(store.root))


def cmd_status(args: argparse.Namespace) -> None:
    store = find_store(override=args.store)
    status = store.status()
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return
    print(f"Store: {status['store']}")
    print(f"Studies: {status['studies']}")
    print(f"Runs: {status['runs']}")
    print(f"Incomplete runs: {status['incomplete_runs']}")


def cmd_show(args: argparse.Namespace) -> None:
    store = find_store(override=args.store)
    if args.run_id:
        meta = store.load_run_meta(args.id, args.run_id)
        if args.trace:
            trace_path = store.study_dir(args.id) / "runs" / args.run_id / "trace.jsonl"
            meta["trace"] = _read_trace_lines(trace_path)
        if args.json:
            print(json.dumps(meta, indent=2, sort_keys=True))
            return
        print(f"Run: {meta.get('run_id')}")
        print(f"Outcome: {meta.get('outcome')}")
        print(f"Steps: {meta.get('steps_taken')}")
        print(f"Final URL: {meta.get('final_url')}")
        if args.trace:
            for event in meta.get("trace", []):
                action = event.get("action") or {}
                print(f"  step {event.get('step')}: {action.get('type')} {action.get('ref') or ''} -> {event.get('status')}")
        return

    study = store.load_study(args.id)
    if args.json:
        print(json.dumps(study, indent=2, sort_keys=True))
        return
    print(f"Study: {study.get('id')}")
    print(f"Title: {study.get('title')}")
    print(f"Status: {study.get('status')}")
    print(f"URL: {study.get('url')}")
    print(f"Personas: {', '.join(study.get('personas') or [])}")


def cmd_analyze(args: argparse.Namespace) -> None:
    from .analyze import analyze_study

    store = find_store(override=args.store)
    findings_path, scores_path, report_path, log_path = analyze_study(
        store,
        args.id,
        include_interrupted=args.include_interrupted,
        driver=args.driver,
    )
    print(findings_path.relative_to(store.root))
    print(scores_path.relative_to(store.root))
    print(report_path.relative_to(store.root))
    print(log_path.relative_to(store.root))


def cmd_uxr(args: argparse.Namespace) -> None:
    from .store import read_json
    from .uxr import write_uxr_artifacts

    store = find_store(override=args.store)
    study = store.load_study(args.id)
    analysis_dir = store.study_dir(args.id) / "analysis"
    findings_path = analysis_dir / "findings.json"
    scores_path = analysis_dir / "scores.json"
    if not findings_path.exists() or not scores_path.exists():
        raise StoreError(f"Study {args.id!r} has no analysis outputs. Run `uxtest analyze {args.id}` first.", exit_code=2)
    plan_path, report_path, protocol_path = write_uxr_artifacts(
        analysis_dir,
        study=study,
        findings=read_json(findings_path),
        scores=read_json(scores_path),
    )
    print(plan_path.relative_to(store.root))
    print(report_path.relative_to(store.root))
    print(protocol_path.relative_to(store.root))


def cmd_animate(args: argparse.Namespace) -> None:
    from .animate import animate_study

    store = find_store(override=args.store)
    index_path = animate_study(store, args.id, delay_cs=args.delay, max_width=args.max_width)
    print(index_path.relative_to(store.root))
    if args.open:
        subprocess.run(["open", str(index_path)], check=False)


def cmd_eval(args: argparse.Namespace) -> None:
    from .eval import evaluate_study

    store = find_store(override=args.store)
    json_path, html_path = evaluate_study(
        store,
        args.id,
        expect_path=args.expect,
        variant=args.variant,
        policy=args.policy,
        minimum_recovered_expected=args.minimum_recovered_expected,
    )
    print(json_path.relative_to(store.root))
    print(html_path.relative_to(store.root))
    if args.open:
        subprocess.run(["open", str(html_path)], check=False)


def cmd_ci(args: argparse.Namespace) -> None:
    from .fixtures import run_fixture

    try:
        store = find_store(override=args.store)
    except StoreError as exc:
        if exc.exit_code != 3:
            raise
        store = Store.init(Path.cwd(), project_name="uxtest-ci")
        print(f"Initialized {store.path}")
    failures: list[str] = []
    for fixture_path in args.fixtures:
        try:
            result = run_fixture(store, fixture_path, open_report=args.open)
        except StoreError as exc:
            failures.append(f"{fixture_path}: {exc}")
            continue
        for artifact in result["artifacts"]:
            print(artifact.relative_to(store.root))
        for pruned in result.get("pruned_runs") or []:
            print(f"pruned {pruned.relative_to(store.root)}")
    if failures:
        raise StoreError("CI fixture failures: " + "; ".join(failures), exit_code=1)


def cmd_prune(args: argparse.Namespace) -> None:
    from .retention import prune_study_runs

    store = find_store(override=args.store)
    pruned = prune_study_runs(store, args.id, keep=args.keep, dry_run=args.dry_run)
    action = "would prune" if args.dry_run else "pruned"
    for run_dir in pruned:
        print(f"{action} {run_dir.relative_to(store.root)}")
    if not pruned:
        print("No runs to prune.")


def cmd_example_serve(args: argparse.Namespace) -> None:
    server = Path(__file__).resolve().parent.parent / "examples" / "checkout_site" / "server.py"
    subprocess.run(
        [sys.executable, str(server), "--host", args.host, "--port", str(args.port)],
        check=True,
    )


def cmd_example_serve_saas(args: argparse.Namespace) -> None:
    server = Path(__file__).resolve().parent.parent / "examples" / "saas_site" / "server.py"
    subprocess.run(
        [sys.executable, str(server), "--host", args.host, "--port", str(args.port)],
        check=True,
    )


def cmd_example_run(args: argparse.Namespace) -> None:
    from .analyze import analyze_study
    from .runner import run_study

    server_process = _ensure_example_server(args.host, args.port)
    try:
        try:
            store = find_store(override=args.store)
        except StoreError as exc:
            if exc.exit_code != 3:
                raise
            store = Store.init(Path.cwd(), project_name="uxtest-example")
            print(f"Initialized {store.path}")

        _ensure_example_personas(store)
        study_id = _ensure_example_study(
            store,
            args.host,
            args.port,
            args.variant,
            personas=["seniors"],
            runs_per_persona=1,
        )
        run_dirs = run_study(
            store,
            study_id,
            max_steps=args.max_steps,
            driver=args.driver,
            max_concurrent_runs=args.max_concurrent_runs,
            continue_on_error=True,
        )
        findings_path, scores_path, report_path, log_path = analyze_study(store, study_id, include_interrupted=True)
        for run_dir in run_dirs:
            print(run_dir.relative_to(store.root))
        print(findings_path.relative_to(store.root))
        print(scores_path.relative_to(store.root))
        print(report_path.relative_to(store.root))
        print(log_path.relative_to(store.root))
        if not args.no_open:
            subprocess.run(["open", str(log_path)], check=False)
    finally:
        if server_process is not None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()


def cmd_example_compare(args: argparse.Namespace) -> None:
    from .analyze import analyze_study
    from .comparison import write_comparison_report
    from .runner import run_study

    server_process = _ensure_example_server(args.host, args.port)
    try:
        try:
            store = find_store(override=args.store)
        except StoreError as exc:
            if exc.exit_code != 3:
                raise
            store = Store.init(Path.cwd(), project_name="uxtest-example")
            print(f"Initialized {store.path}")

        personas = args.personas or list(EXAMPLE_PERSONAS)
        _ensure_example_personas(store, personas=personas)
        study_ids: list[str] = []
        for variant in ("confusing", "clear"):
            study_id = _ensure_example_study(
                store,
                args.host,
                args.port,
                variant,
                personas=personas,
                runs_per_persona=args.runs_per_persona,
            )
            study_ids.append(study_id)
            run_dirs = run_study(
                store,
                study_id,
                max_steps=args.max_steps,
                driver=args.driver,
                max_concurrent_runs=args.max_concurrent_runs,
                continue_on_error=True,
            )
            findings_path, scores_path, report_path, log_path = analyze_study(
                store,
                study_id,
                include_interrupted=True,
                driver=args.analysis_driver,
            )
            for run_dir in run_dirs:
                print(run_dir.relative_to(store.root))
            print(findings_path.relative_to(store.root))
            print(scores_path.relative_to(store.root))
            print(report_path.relative_to(store.root))
            print(log_path.relative_to(store.root))

        comparison_path = write_comparison_report(
            store,
            title="Checkout Example Comparison",
            study_ids=study_ids,
            output_name="checkout-clear-vs-confusing.html",
        )
        print(comparison_path.relative_to(store.root))
        if not args.no_open:
            subprocess.run(["open", str(comparison_path)], check=False)
    finally:
        if server_process is not None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()


def cmd_example_eval_saas(args: argparse.Namespace) -> None:
    from .fixtures import run_fixture

    try:
        store = find_store(override=args.store)
    except StoreError as exc:
        if exc.exit_code != 3:
            raise
        store = Store.init(Path.cwd(), project_name="uxtest-example")
        print(f"Initialized {store.path}")
    fixture_path = Path(__file__).resolve().parent.parent / "examples" / "saas_site" / "regression.yaml"
    result = run_fixture(
        store,
        fixture_path,
        open_report=not args.no_open,
        overrides={
            "server": {"host": args.host, "port": args.port},
            "max_steps": args.max_steps,
            "animation_delay": args.delay,
        },
    )
    for artifact in result["artifacts"]:
        print(artifact.relative_to(store.root))
    for pruned in result.get("pruned_runs") or []:
        print(f"pruned {pruned.relative_to(store.root)}")


def _ensure_example_server(host: str, port: int) -> subprocess.Popen | None:
    if _port_is_open(host, port):
        return None
    server = Path(__file__).resolve().parent.parent / "examples" / "checkout_site" / "server.py"
    process = subprocess.Popen(
        [sys.executable, str(server), "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 5
    while time.time() < deadline:
        if _port_is_open(host, port):
            return process
        time.sleep(0.1)
    process.terminate()
    raise StoreError(f"Example server did not start on {host}:{port}.", exit_code=1)


def _ensure_saas_server(host: str, port: int) -> subprocess.Popen | None:
    if _port_is_open(host, port):
        return None
    server = Path(__file__).resolve().parent.parent / "examples" / "saas_site" / "server.py"
    process = subprocess.Popen(
        [sys.executable, str(server), "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 5
    while time.time() < deadline:
        if _port_is_open(host, port):
            return process
        time.sleep(0.1)
    process.terminate()
    raise StoreError(f"SaaS example server did not start on {host}:{port}.", exit_code=1)


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


EXAMPLE_PERSONAS: dict[str, dict] = {
    "seniors": {
        "schema_version": 1,
        "name": "seniors",
        "description": "Desktop shopper with moderate web familiarity",
        "attributes": {
            "age_range": [35, 55],
            "tech_literacy": "medium",
            "reading_style": "skims",
            "patience": "medium",
            "device_familiarity": "desktop",
        },
        "accessibility": {},
        "goals_bias": "Prefers clear labels, predictable checkout steps, and helpful error messages.",
        "frustration": {"threshold": 7, "per_step_decay": 1},
    },
    "low-confidence": {
        "schema_version": 1,
        "name": "low-confidence",
        "description": "Cautious shopper who hesitates when labels or errors are unclear",
        "attributes": {
            "age_range": [45, 70],
            "tech_literacy": "low",
            "reading_style": "reads carefully",
            "patience": "low",
            "device_familiarity": "desktop",
        },
        "accessibility": {"prefers_large_targets": True},
        "goals_bias": "Needs plain labels, visible reassurance, and clear recovery from mistakes.",
        "frustration": {"threshold": 5, "per_step_decay": 1},
    },
    "mobile-first": {
        "schema_version": 1,
        "name": "mobile-first",
        "description": "Phone-first shopper who expects compact, direct checkout flows",
        "attributes": {
            "age_range": [20, 40],
            "tech_literacy": "high",
            "reading_style": "scans headings",
            "patience": "medium",
            "device_familiarity": "mobile",
        },
        "accessibility": {},
        "goals_bias": "Looks for fast checkout, visible primary actions, and minimal form friction.",
        "frustration": {"threshold": 6, "per_step_decay": 1},
    },
    "price-sensitive": {
        "schema_version": 1,
        "name": "price-sensitive",
        "description": "Skimming shopper who checks totals and fees before committing",
        "attributes": {
            "age_range": [25, 60],
            "tech_literacy": "medium",
            "reading_style": "skims prices",
            "patience": "medium",
            "device_familiarity": "desktop",
        },
        "accessibility": {},
        "goals_bias": "Focuses on total cost, fees, trust signals, and whether the final order action is safe.",
        "frustration": {"threshold": 6, "per_step_decay": 1},
    },
}


def _ensure_example_personas(store: Store, *, personas: list[str] | None = None) -> None:
    names = personas or list(EXAMPLE_PERSONAS)
    for name in names:
        if name not in EXAMPLE_PERSONAS:
            if not (store.personas_path / f"{name}.yaml").exists():
                raise StoreError(f"Example persona {name!r} is not built in and does not exist.", exit_code=2)
            continue
        store.write_persona(EXAMPLE_PERSONAS[name])


def _ensure_example_study(
    store: Store,
    host: str,
    port: int,
    variant: str,
    *,
    personas: list[str],
    runs_per_persona: int,
) -> str:
    title = f"Checkout Flow ({variant})"
    url = f"http://{host}:{port}/?variant={variant}"
    task = (
        "Buy the breakfast bundle as a guest and reach the confirmation page. "
        "Use email tester@example.com, name Test Shopper, card number 4242424242424242, and ZIP code 02139."
    )
    success_criteria = "Order confirmed and order number are visible."
    for study in store.list_studies():
        if study.get("title") == title and "uxtest-example" in (study.get("tags") or []):
            study["url"] = url
            study["task"] = task
            study["success_criteria"] = success_criteria
            study["personas"] = personas
            study["runs_per_persona"] = runs_per_persona
            tags = set(study.get("tags") or [])
            tags.update({"uxtest-example", f"variant-{variant}"})
            study["tags"] = sorted(tags)
            store.write_study(study)
            return str(study["id"])
    study_dir = store.create_study(
        title,
        task=task,
        url=url,
        success_criteria=success_criteria,
        personas=personas,
        runs_per_persona=runs_per_persona,
        tags=["uxtest-example", f"variant-{variant}"],
    )
    return study_dir.name


def _ensure_saas_study(store: Store, host: str, port: int, variant: str) -> str:
    title = f"Northstar SaaS Fixture ({variant})"
    url = f"http://{host}:{port}/?variant={variant}"
    task = (
        "You are evaluating Northstar, a B2B research platform. "
        "Figure out which product area you would explore next and identify anything confusing."
    )
    success_criteria = "The product areas, docs route, or quickstart route have been inspected."
    for study in store.list_studies():
        if study.get("title") == title and "uxtest-saas-fixture" in (study.get("tags") or []):
            study["url"] = url
            study["task"] = task
            study["success_criteria"] = success_criteria
            study["personas"] = ["mobile-first"]
            study["runs_per_persona"] = 1
            tags = set(study.get("tags") or [])
            tags.update({"uxtest-saas-fixture", f"variant-{variant}"})
            study["tags"] = sorted(tags)
            store.write_study(study)
            return str(study["id"])
    study_dir = store.create_study(
        title,
        task=task,
        url=url,
        success_criteria=success_criteria,
        personas=["mobile-first"],
        runs_per_persona=1,
        tags=["uxtest-saas-fixture", f"variant-{variant}"],
    )
    return study_dir.name


def _read_trace_lines(path: Path) -> list[dict]:
    events: list[dict] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                break
            if isinstance(value, dict):
                events.append(value)
    return events


DEVICE_PROFILES: dict[str, dict] = {
    "desktop": {
        "viewport": {"width": 1280, "height": 800},
        "is_mobile": False,
        "has_touch": False,
        "device_scale_factor": 1,
    },
    "iphone": {
        "viewport": {"width": 390, "height": 844},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 3,
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    },
    "pixel": {
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2.625,
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    },
}


def _run_overrides_from_args(args: argparse.Namespace) -> dict | None:
    overrides: dict = {}
    if getattr(args, "device", None):
        overrides.update(DEVICE_PROFILES[args.device])
    if getattr(args, "viewport", None):
        overrides["viewport"] = _parse_viewport(args.viewport)
    if getattr(args, "mobile", False):
        overrides["is_mobile"] = True
    if getattr(args, "touch", False):
        overrides["has_touch"] = True
    if getattr(args, "device_scale_factor", None) is not None:
        overrides["device_scale_factor"] = args.device_scale_factor
    if getattr(args, "user_agent", None):
        overrides["user_agent"] = args.user_agent
    return overrides or None


def _parse_viewport(value: str) -> dict[str, int]:
    normalized = value.lower().replace("×", "x")
    if "x" not in normalized:
        raise StoreError(f"Viewport must be WIDTHxHEIGHT, got {value!r}.", exit_code=2)
    width, height = normalized.split("x", 1)
    try:
        parsed = {"width": int(width), "height": int(height)}
    except ValueError as exc:
        raise StoreError(f"Viewport must be WIDTHxHEIGHT, got {value!r}.", exit_code=2) from exc
    if parsed["width"] <= 0 or parsed["height"] <= 0:
        raise StoreError(f"Viewport dimensions must be positive, got {value!r}.", exit_code=2)
    return parsed
