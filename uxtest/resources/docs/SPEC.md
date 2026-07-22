# Spec: `uxtest_store` File-Based Project Store

**Status:** Draft
**Version:** 0.1.0
**Last updated:** 2026-06-12

## 1. Overview

`uxtest` is a Python CLI that runs synthetic-user UX studies against live web
applications using an LLM-driven agent loop and Playwright browser automation.
This document specifies the **file-based project store**: a `uxtest_store/`
directory that holds all project state — study requests, run traces,
screenshots, accessibility audits, analysis output, and configuration.

### 1.1 Goals

- **File-based, no database.** All state is plain files (YAML, JSON, JSONL,
  PNG, HTML). Anything the CLI knows, a human can read with `cat` and `ls`.
- **Inspectable and greppable.** Traces and findings are line-oriented or
  pretty-printed JSON so standard tooling (grep, jq, diff) works.
- **Reproducible.** Every run snapshots the exact inputs (persona, config,
  prompts metadata) that produced it. Re-running a study later is comparable
  to past runs.
- **Crash-safe.** A killed process leaves valid partial data, never a
  corrupted store.
- **Version-control friendly.** Requests (configs, personas, study
  definitions) are small text files intended to be committed; bulky derived
  data is easy to ignore.
- **Idempotent-ish execution.** Re-running a study appends new runs; it never
  silently overwrites existing data.

### 1.2 Non-Goals

- Multi-machine or concurrent multi-user access (single workstation, single
  writer per study).
- A query layer or index beyond directory walking. If a project outgrows
  filesystem walks, that is a future, separate feature.
- Remote/cloud storage backends (could layer on later via sync).

## 2. Concepts

| Term | Definition |
|---|---|
| **Project** | A directory tree rooted at the parent of a `uxtest_store/` directory. One project per product/site under test, typically. |
| **Persona** | A named synthetic-user profile (demographics, goals, tech literacy, patience, accessibility needs) defined in YAML. |
| **Study** | A single research request: one task + target URL + persona set + run count. The unit of execution, analysis, and comparison. |
| **Run** | One agent session: one persona instance attempting the study task once. Produces a trace, screenshots, and per-page audits. |
| **Trace** | The step-by-step record of a run: page state references, actions, think-aloud reasoning, frustration scores. |
| **Analysis** | Derived artifacts produced from one or more runs: findings, scores, reports. Always regenerable from raw run data. |

## 3. Directory Layout

```
uxtest_store/
├── config.yaml                     # project defaults
├── personas/
│   ├── seniors.yaml
│   └── power-users.yaml
├── studies/
│   └── 2026-06-12-checkout-flow/
│       ├── study.yaml              # the request (committed)
│       ├── runs/
│       │   ├── run-001-seniors-a3f2/
│       │   │   ├── meta.json
│       │   │   ├── trace.jsonl
│       │   │   ├── screenshots/
│       │   │   │   ├── step-001.png
│       │   │   │   └── step-002.png
│       │   │   └── a11y/
│       │   │       └── step-001.json
│       │   └── run-002-seniors-9b1c/
│       └── analysis/
│           ├── findings.json
│           ├── scores.json
│           └── report.html
├── cache/
│   └── llm/
│       └── <first2>/<sha256>.json
├── locks/
│   └── 2026-06-12-checkout-flow.lock
└── .gitignore                      # written by `uxtest init` (see §12)
```

### 3.1 Path rules

- All paths inside `uxtest_store/` are relative; the store must be relocatable
  (moving the project directory must not break anything).
- Directory and file names are restricted to `[a-z0-9._-]` to stay portable
  across macOS, Linux, and Windows.
- Maximum nesting is fixed by this spec; tools must not invent deeper
  structures under `runs/` or `analysis/` beyond those defined here.

## 4. Store Discovery and Initialization

### 4.1 Discovery

Commands locate the store by walking up from the current working directory
(like `git`), stopping at the first directory containing `uxtest_store/`. The
`UXTEST_DIR` environment variable, or a global `--store PATH` flag, overrides
discovery. If no store is found, commands that need one exit with code `3`
and a hint to run `uxtest init`.

### 4.2 `uxtest init`

Creates:

- `uxtest_store/config.yaml` with commented defaults
- `uxtest_store/personas/` containing one example persona
- empty `studies/`, `cache/`, `locks/`
- `uxtest_store/.gitignore` per §12

`init` refuses to run inside an existing store unless `--force` is given;
`--force` only rewrites `config.yaml` defaults and never touches `studies/`.

## 5. File Formats

All YAML files are UTF-8, parsed in safe mode. All JSON files are UTF-8 with
a trailing newline. Every structured file carries a `schema_version` field
(see §11).

### 5.1 `config.yaml` — project defaults

```yaml
schema_version: 1
project_name: acme-checkout

defaults:
  model: claude-sonnet-4-6
  temperature: 0.7
  max_steps: 30
  viewport: { width: 1280, height: 800 }
  screenshot: full          # full | viewport | off
  screenshot_format: png     # png | jpeg
  screenshot_quality: 80    # JPEG quality when screenshot_format is jpeg
  a11y_audit: true          # run axe-core on each new page state
  runs_per_persona: 5

browser:
  engine: chromium          # chromium | firefox | webkit
  headless: true
  slow_mo_ms: 0

secrets:
  env_file: secrets.env      # git-ignored; optional
  redact_patterns: []        # regexes applied to typed text and trace fields
```

Precedence (lowest → highest): built-in defaults → `config.yaml` →
`study.yaml` overrides → CLI flags.

### 5.2 `personas/<name>.yaml`

```yaml
schema_version: 1
name: seniors
description: Retired adults, 65+, low-to-moderate tech confidence
attributes:
  age_range: [65, 80]
  tech_literacy: low        # low | medium | high
  reading_style: skims      # skims | reads-carefully
  patience: low             # maps to frustration threshold
  device_familiarity: desktop
accessibility:
  vision: reduced-contrast-sensitivity   # optional simulation hints
goals_bias: >
  Prefers obvious, labeled buttons. Distrusts forms that ask for
  unnecessary information. Gives up quickly when error messages
  are vague.
frustration:
  threshold: 6              # 0–10; at/above this the persona abandons
  per_step_decay: 1         # recovery when steps go smoothly
```

The persona file is a *template*. At run time it is resolved (ranges sampled,
defaults filled) into a concrete **persona instance**, which is what gets
snapshotted into the run (§5.4).

### 5.3 `studies/<study-id>/study.yaml` — the request

```yaml
schema_version: 1
id: 2026-06-12-checkout-flow
title: Checkout flow friction
created_at: 2026-06-12T14:03:22Z
status: complete            # draft | running | complete | failed
task: >
  Starting from the homepage, add any product to the cart and complete
  checkout as a guest using the test credit card.
url: https://staging.acme.example/
success_criteria: >
  An order confirmation page is reached and an order number is visible.
personas: [seniors, power-users]
runs_per_persona: 10        # overrides config default
overrides:                  # optional per-study config overrides
  model: gpt-4o
  max_steps: 40
tags: [checkout, q2-redesign]
```

Rules:

- `id` equals the directory name and is immutable after creation.
- `study.yaml` is the only file in the study directory a user is expected to
  edit by hand, and only while `status: draft`.
- Editing `task`, `url`, or `personas` after runs exist is rejected by the
  CLI (`uxtest study edit` enforces this); the right move is a new study.

### 5.4 `runs/<run-id>/meta.json`

Created at run start (with `outcome: null`) and atomically rewritten at run
end with the finalized outcome. Contains everything needed to interpret the
trace without consulting mutable project files.

```json
{
  "schema_version": 1,
  "run_id": "run-001-seniors-a3f2",
  "study_id": "2026-06-12-checkout-flow",
  "started_at": "2026-06-12T14:10:01Z",
  "finished_at": "2026-06-12T14:13:47Z",
  "outcome": "gave_up",
  "outcome_detail": "Frustration threshold reached on /checkout/payment",
  "steps_taken": 17,
  "final_url": "https://staging.acme.example/checkout/payment",
  "seed": 91842,
  "persona_instance": {
    "name": "seniors",
    "resolved": { "age": 71, "tech_literacy": "low", "patience": "low" },
    "source_sha256": "ab12…",
    "snapshot": { "… full resolved persona document …": true }
  },
  "resolved_config": {
    "model": "claude-sonnet-4-6",
    "temperature": 0.7,
    "max_steps": 40,
    "viewport": { "width": 1280, "height": 800 }
  },
  "environment": {
    "uxtest_version": "0.4.1",
    "playwright_version": "1.52.0",
    "browser": "chromium",
    "os": "darwin-arm64"
  },
  "costs": { "llm_input_tokens": 184223, "llm_output_tokens": 9120 }
}
```

`outcome` is one of: `done` (success criteria met), `gave_up` (frustration
abandonment), `max_steps`, `error` (tool/browser failure), `interrupted`
(SIGINT/crash detected on next CLI invocation; see §8.3).

### 5.5 `runs/<run-id>/trace.jsonl`

Append-only, one JSON object per line, one line per agent step. A run is
valid even if truncated mid-write at any line boundary; a partial final line
is discarded by readers.

```json
{"schema_version": 1, "event_type": "step", "step": 3,
 "ts": "2026-06-12T14:10:31Z",
 "url": "https://staging.acme.example/cart",
 "page_title": "Your Cart",
 "observation": {"screenshot": "screenshots/step-003.png",
                  "a11y_audit": "a11y/step-003.json",
                  "interactive_elements": 24,
                  "interactive_elements_sample": [{"ref": "e14", "tag": "button", "label": "Continue"}],
                  "visible_text_preview": "Your cart..."},
 "model_decision": {"driver": "edsl",
                    "thinking": "I found the cart. There are two buttons that both look like checkout.",
                    "frustration": 4,
                    "status": "continue",
                    "raw_response": "{\"action_type\":\"click\",...}",
                    "edsl": {"agent_name": "seniors",
                             "agent_traits": {"tech_literacy": "medium"},
                             "model": "gpt-4o",
                             "question_name": "browser_decision"}},
 "thinking": "I found the cart. There are two buttons that both look like checkout — 'Continue' and 'Express Pay'. I'm not sure which is the normal one.",
 "frustration": 4,
 "action": {"type": "click", "ref": "e14", "label": "Continue",
             "selector_hint": "role=button[name=\"Continue\"]"},
 "result": {"ok": true, "navigation": true, "console_errors": 0},
 "status": "continue"}
```

Field notes:

- `step` is 1-based and strictly increasing.
- `event_type` is currently `step`; future event types may split
  observation, model decision, action result, and tool errors into separate
  lines if a run needs finer-grained streaming.
- `action.type` ∈ `click | type | scroll | select | back | wait | none`.
  `type` actions include a `text` field; secret values are redacted to
  `"«redacted»"` if they match configured secret patterns
  (`secrets.redact_patterns` in `config.yaml` plus known values loaded from
  `secrets.env`).
- `status` ∈ `continue | done | gave_up` — the agent's own assessment; the
  authoritative outcome lives in `meta.json`.
- `model_decision` stores the driver (`edsl` or `heuristic`), rationale,
  frustration, EDSL agent/model metadata, and raw model response where
  available. Secret values must be redacted before persistence.
- Screenshot and audit paths are relative to the run directory.

### 5.6 `runs/<run-id>/a11y/step-NNN.json`

Raw axe-core results for the page state at that step, captured only when the
URL or DOM materially changed (not on every scroll). Stored verbatim from
axe plus an envelope:

```json
{"schema_version": 1, "step": 3, "url": "…", "axe_version": "4.10",
 "violations": [ { "id": "color-contrast", "impact": "serious", "nodes": 7 } ],
 "raw": { "…full axe output…": true }}
```

### 5.7 `analysis/findings.json`

The standardized, cross-study-comparable output of `uxtest analyze`.
Regenerable at any time from `runs/`.

```json
{
  "schema_version": 1,
  "study_id": "2026-06-12-checkout-flow",
  "generated_at": "2026-06-12T15:02:10Z",
  "analyzer": { "model": "claude-sonnet-4-6", "prompt_sha256": "9f31…" },
  "runs_analyzed": 20,
  "findings": [
    {
      "finding_id": "f-001",
      "category": "navigation",
      "severity": "high",
      "title": "Two competing checkout CTAs on the cart page",
      "description": "…",
      "frequency": { "affected_runs": 14, "total_runs": 20 },
      "personas_affected": ["seniors", "power-users"],
      "locations": [
        { "url_path": "/cart", "page_title": "Your Cart" }
      ],
      "evidence": [
        { "run_id": "run-001-seniors-a3f2", "steps": [3, 4],
          "screenshot": "runs/run-001-seniors-a3f2/screenshots/step-003.png" }
      ],
      "wcag_refs": []
    }
  ]
}
```

Controlled vocabularies (stable across spec versions so studies can be
diffed over time):

- `category` ∈ `navigation | copy-clarity | layout | trust | performance |
  accessibility | form-design | error-handling`
- `severity` ∈ `low | medium | high | critical`

### 5.8 `analysis/scores.json`

Aggregate metrics: task completion rate, mean steps to completion, mean/max
frustration, abandonment points (URL histogram), synthetic SUS-style score
with an explicit `methodology` string. Same regeneration rules as findings.
Like `findings.json`, this file is pretty-printed with deterministic key
ordering where practical so it can be reviewed in diffs.

### 5.9 `analysis/report.html`

Technical evidence dashboard with inline CSS and relative links to retained run
screenshots, rendering findings, scores, and selected trace excerpts without
duplicating large image payloads inside the HTML.
It is an inspectable package view, not the final stakeholder narrative.
Derived; never the source of truth.

### 5.10 `analysis/log.html`

Self-contained single-file HTML for the system builder. It renders every run
in detail: `meta.json`, resolved persona snapshot, resolved config,
environment, per-step screenshot, visible text preview, interactive element
sample, EDSL/model decision metadata, raw model response where available,
browser action, action result, and the full trace event. Derived; never the
source of truth.

## 6. Identifiers and Naming

- **Study ID:** `YYYY-MM-DD-<slug>` where slug is `[a-z0-9-]{1,40}`,
  generated from the title and uniquified with `-2`, `-3`, … on collision.
- **Run ID:** `run-NNN-<persona>-<hash4>` where `NNN` is a zero-padded
  per-study sequence across all personas, `<persona>` is the persona name,
  and `<hash4>` is the first 4 hex chars of a random UUID. Sequence numbers
  are assigned under the study lock (§8).
- **Finding ID:** `f-NNN`, scoped to a single `findings.json`.

## 7. Lifecycle and Status Model

```
            uxtest study new            uxtest study run             all runs finished
  (none) ───────────────────▶ draft ───────────────────▶ running ───────────────────▶ complete
                                                            │
                                                            └──── unrecoverable error ──▶ failed
```

- `status` lives in `study.yaml` and is updated by the CLI under the study
  lock. `complete` does not prevent further runs; a subsequent
  `uxtest study run` moves it back to `running`, then `complete`.
- Run-level state is *implicit in files*: a run directory with
  `meta.json.outcome == null` and no live lock is **stale** (§8.3).
- `uxtest status` derives everything by walking the tree — there is no
  separate state file to drift out of sync.

## 8. Concurrency and Crash Safety

### 8.1 Locking

- Lock granularity is the **study**. A lock file
  `locks/<study-id>.lock` contains `{pid, hostname, started_at}`.
- Locks are advisory and acquired with `O_CREAT|O_EXCL`. Different studies
  may run concurrently; two writers on one study may not.
- A lock whose PID is dead (same hostname) is considered stale and may be
  broken automatically; otherwise `--break-lock` is required.

### 8.2 Atomic writes

Every non-append file (`meta.json`, `study.yaml`, analysis outputs) is
written via *temp file in the same directory + `fsync` + atomic rename*.
JSONL traces are append-only with line-buffered flushes.

### 8.3 Crash recovery

On any CLI invocation that touches a study, runs with `outcome: null` and no
live lock are finalized as `outcome: "interrupted"`. Their traces remain
valid up to the last complete line and are included in analysis only with
`--include-interrupted`.

## 9. LLM Cache

- Location: `cache/llm/<first2>/<sha256>.json`, keyed by SHA-256 of the
  canonicalized request (model, system prompt, messages, temperature, seed).
- Used by default for **analysis** (deterministic re-analysis is cheap) and
  disabled by default for **agent steps** (variance across runs is the
  point); `--cache/--no-cache` overrides either.
- Cache is always safe to delete; `uxtest gc --cache` clears it.

## 10. Storage Management

- Screenshots dominate disk usage. Controls: `screenshot: full|viewport|off`,
  `screenshot_format`, JPEG quality, and capture-on-change-only (default).
- `uxtest gc` policies:
  - `--screenshots --older-than 90d`: delete screenshots from old runs,
    keeping those referenced as `evidence` in any `findings.json`.
  - `--runs --keep-last N --per-study`: prune oldest run directories.
  - `--cache`: clear the LLM cache.
- `gc` writes a `gc.log` line per deletion under `uxtest_store/` for audit.
- `uxtest study archive <id>` tars a study directory to
  `studies/<id>.tar.zst` and removes the directory; `unarchive` reverses it.

## 11. Schema Versioning and Migration

- Every structured file carries an integer `schema_version`.
- Readers accept the current version and all prior versions for which a
  migration exists; `uxtest migrate` upgrades files in place (atomic writes,
  with `--dry-run`).
- Unknown *fields* are preserved on rewrite (forward compatibility); unknown
  *versions* are a hard error naming the file.

## 12. Version Control Guidance

`uxtest init` writes `uxtest_store/.gitignore`:

```gitignore
# Derived and bulky data — keep out of git
studies/*/runs/
studies/*/analysis/report.html
studies/*/analysis/log.html
cache/
locks/
gc.log
```

Intended to be committed: `config.yaml`, `personas/`, every `study.yaml`,
and (team's choice) `findings.json` + `scores.json`, which are small,
pretty-printed, and diff well in code review.

## 13. CLI ↔ Store Mapping

| Command | Reads | Writes |
|---|---|---|
| `uxtest init` | — | store skeleton |
| `uxtest persona new <name>` | — | `personas/<name>.yaml` |
| `uxtest study new <slug> --task … --url …` | config | `studies/<id>/study.yaml` (status `draft`) |
| `uxtest study run <id>` | study, personas, config | lock; run dirs (`meta.json`, `trace.jsonl`, screenshots, a11y); study status |
| `uxtest study list` | walk `studies/` | — |
| `uxtest status` | walk store | finalizes stale runs (§8.3) |
| `uxtest show <id> [run-id]` | study/run files | — |
| `uxtest analyze <id>` | `runs/`, cache | `analysis/findings.json`, `analysis/scores.json`, `analysis/report.html`, `analysis/log.html` |
| `uxtest report guide <id>` | study, runs, analysis artifacts | structured evidence inventory and writing guidance to stdout |
| `uxtest report template <id>` | study, runs, analysis artifacts | study-specific Markdown scaffold to stdout; no report file |
| `uxtest example serve` | example site files | localhost checkout fixture server |
| `uxtest example run` | example site files, store if present | optional store skeleton; example study; run dirs; analysis outputs |
| `uxtest compare <id-a> <id-b>` | two `findings.json` + `scores.json` | report to stdout / `--out` |
| `uxtest gc` / `archive` | walk store | deletions / tarballs, `gc.log` |
| `uxtest migrate` | all structured files | upgraded files |

Exit codes: `0` success · `1` runtime failure · `2` usage error ·
`3` no store found · `4` lock held.

## 14. Cross-Study Comparison

Because `findings.json` and `scores.json` use stable controlled
vocabularies (§5.7) and carry `study_id` + analyzer provenance,
`uxtest compare` can:

- match findings across studies by `(category, normalized URL path,
  fuzzy-title similarity)` using `findings[].locations[]`, and report
  resolved / persisting / new issues;
- diff completion rate, mean frustration, and abandonment histograms;
- emit a markdown or HTML delta report suitable for "did the redesign
  help?" reviews.

Comparison never reads raw traces; if richer matching is needed later, it
must be added to the findings schema first (and version-bumped).

## 15. Security and Privacy Notes

- Test credentials and secrets must come from environment variables or a
  git-ignored `secrets.env`; the agent's typed text is redacted in traces
  per configured patterns and known secret values (§5.1, §5.5).
- Screenshots may capture sensitive data on real sites; `gc` and
  `screenshot: off` are the mitigations, and the docs must call this out.
- The store contains LLM prompts/outputs in `cache/`; treat the whole
  `uxtest_store/` directory as project-confidential by default.

## 16. Open Questions

1. Should persona *instances* be promotable to first-class reusable files
   (e.g., pinning an exact sampled persona for regression testing)?
2. Is per-step DOM/ARIA snapshot storage worth the disk cost for deeper
   re-analysis, perhaps behind a `--record-dom` flag?
3. Multi-variant studies (built-in A/B: two URLs, shared task) — one study
   with `variants:` or two studies + `compare`? Leaning toward `variants:`
   as a v2 schema addition.
4. Should `compare` support more than two studies (trend lines over many
   studies)? Likely yes, once the matching heuristics in §14 are proven.

## 17. EDSL Integration Plan

`uxtest` should use EDSL for the research and inference layer, while keeping
browser automation and the `uxtest_store/` store in this package. This keeps v1
small: EDSL already provides agents, scenario parameterization, vision-capable
file inputs, model selection, caching, and structured results; `uxtest` adds
the browser-control loop and UX-study file layout.

### 17.1 Concept mapping

| `uxtest` concept | EDSL concept | Notes |
|---|---|---|
| Persona template | `edsl.Agent` | Persona attributes become agent `traits`; `goals_bias`, accessibility needs, and frustration behavior become `instruction` text and/or codebook entries. |
| Concrete persona instance | `edsl.Agent` snapshot | Resolve ranges and defaults before constructing the agent; persist the resolved traits in `meta.json`. |
| Study/run inputs | `edsl.Scenario` / `ScenarioList` | Study task, URL, run id, step number, current URL, page title, visible text, interactive elements, and screenshot metadata are scenario fields. |
| Screenshot | `edsl.FileStore` | Saved screenshots are attached to the scenario and referenced in question text, e.g. `{{ scenario.screenshot }}`, so vision-capable models receive the image. |
| Decision prompt | `QuestionPydantic` or `QuestionExtract` | Use a structured question for each agent step so the answer validates to one browser action plus rationale/frustration/status. Prefer `QuestionPydantic` when provider schema support is available. |
| Analysis prompt | EDSL survey/job | Run analysis over trace summaries and evidence screenshots, then normalize EDSL results into `findings.json` and `scores.json`. |
| Model config | `edsl.Model` | `resolved_config.model`, temperature, max tokens, and provider-specific settings construct the EDSL model. |
| Cache | EDSL cache + `uxtest_store/cache` | Prefer EDSL's cache machinery for model calls, with an adapter or export step so `uxtest_store/cache/llm/` remains inspectable and deletable. |

### 17.2 V1 execution architecture

In v1, `uxtest` owns Playwright directly and calls EDSL at decision points:

1. Load `study.yaml`, personas, config, and allocate run ids under the study
   lock.
2. Resolve each persona into an EDSL `Agent`.
3. Start a Playwright browser/page for the run.
4. For each step:
   - capture page state: URL, title, visible text summary, accessibility tree
     or interactive element list, screenshot, and optional axe audit;
   - save raw artifacts under the run directory;
   - build an EDSL `Scenario` containing the current state and a `FileStore`
     for the screenshot when screenshots are enabled;
   - ask the EDSL agent/model a structured action-selection question;
   - validate the returned action against allowed actions and known element
     references;
   - execute the action in Playwright;
   - append one line to `trace.jsonl`.
5. Finalize `meta.json` and update `study.yaml` status.

The `uxtest_store/` files are the source of truth. EDSL `Results` objects are useful
intermediate objects, but v1 should not require readers to deserialize EDSL
objects in order to inspect, analyze, or migrate a project store.

### 17.3 Step decision shape

The step prompt should be a structured EDSL question rather than free text.
Prefer `QuestionPydantic` with a browser-action response model; fall back to
`QuestionExtract` if a provider or model path cannot use response schemas. The
validated answer should contain at least:

```json
{
  "action": {
    "type": "click",
    "ref": "e14",
    "text": null,
    "value": null
  },
  "thinking": "Short user-visible rationale for trace inspection.",
  "frustration": 4,
  "status": "continue"
}
```

Allowed `action.type` values are those in §5.5. The model may propose only
element references that `uxtest` supplied in the scenario. If validation fails,
`uxtest` may retry with a repair prompt once; repeated invalid actions end the
run as `outcome: "error"`.

### 17.4 Vision usage

When `screenshot` is not `off`, the scenario should include:

- `screenshot`: an EDSL `FileStore` for the current screenshot;
- `screenshot_path`: the relative run-local path persisted in the trace;
- `visible_text` and `interactive_elements`: text fallbacks for models or
  providers that cannot process images.

This lets vision-capable EDSL models inspect the page directly while preserving
a text-only fallback path for tests, cheaper models, and debugging.

### 17.5 EDSL changes worth upstreaming

The first implementation should avoid adding browser automation to EDSL until
the `uxtest` loop has proven the right abstractions. After that, the reusable
pieces to move into EDSL are:

- a browser-state scenario helper that packages screenshot `FileStore`, URL,
  page title, visible text, and element refs consistently;
- a structured browser-action question or response validator;
- optional Playwright-backed browser tools/session classes for projects that
  want EDSL-native browser studies;
- a trace/result adapter that converts EDSL question results into portable
  JSONL events.

Native Playwright support in EDSL should be an extension point, not a
requirement for reading `uxtest_store/` stores or running analysis.
