# uxtest Agent Guide

This package runs synthetic-user UX studies against live web pages with
Playwright and EDSL. This README is written for coding agents operating the
package from a terminal. It prioritizes execution patterns, artifacts, and
failure modes over product explanation.

## Operating Model

`uxtest` stores all state in `.uxtest/` under the project root:

- `.uxtest/personas/*.yaml`: reusable persona templates.
- `.uxtest/studies/<study-id>/study.yaml`: study request.
- `.uxtest/studies/<study-id>/runs/<run-id>/`: raw browser traces,
  screenshots, and run metadata.
- `.uxtest/studies/<study-id>/analysis/`: generated reports and summaries.
- `.uxtest/comparisons/*.html`: multi-study comparison reports.

Raw traces are the source of truth. Analysis files are derived and can be
regenerated.

## Environment

Run commands from this package root:

```bash
cd /Users/johnhorton/tools/ep/capabilities/packages/uxtest
```

Use `uv run` for CLI and tests:

```bash
uv run uxtest --help
uv run python -m pytest -q tests
```

EDSL is installed from the editable local path in `pyproject.toml`:

```toml
edsl = { path = "../../../edsl", editable = true }
```

Remote inference credentials are expected in `.env`. Do not require an OpenAI
API key for normal EDSL browser runs; the runner uses remote inference.

## Common Workflows

### Run a Fixture

Fixtures are the easiest way to launch a repeatable study:

```bash
uv run uxtest ci examples/jjh_site/targeted.yaml
```

The fixture runner will:

1. Ensure persona YAML exists.
2. Create or update fixture-backed studies.
3. Launch Playwright browser runs.
4. Ask EDSL for browser decisions at each step.
5. Analyze each study.
6. Generate animations, eval outputs, and a comparison HTML report.

Useful existing fixtures:

```bash
uv run uxtest ci examples/saas_site/regression-edsl.yaml
uv run uxtest ci examples/jjh_site/discovery.yaml
uv run uxtest ci examples/jjh_site/targeted.yaml
```

### Study Type Guides

Worked examples for common UXR jobs live under:

- [UXR Study Type Examples](examples/study_types/README.md)
- [Task Discovery Study](examples/study_types/task_discovery/README.md)

Start with Task Discovery when you want to test whether first-time visitors can
understand what a page is for, choose a plausible first action, and explain what
is confusing or missing before they act.

### Create a One-Off Study

Use this when there is no fixture yet:

```bash
uv run uxtest study new "Homepage discovery" \
  --url "https://example.com/" \
  --task "Starting from the homepage, decide what you would click next and why." \
  --success-criteria "The visitor identifies a relevant next action." \
  --persona academic-researcher \
  --runs-per-persona 1
```

Then run:

```bash
uv run uxtest study run <study-id> --driver edsl --max-steps 8 --max-concurrent-runs 2
uv run uxtest analyze <study-id> --include-interrupted
uv run uxtest animate <study-id>
uv run uxtest uxr <study-id>
```

### Use Device Profiles

For ad hoc runs:

```bash
uv run uxtest study run <study-id> --device iphone --driver edsl
uv run uxtest study run <study-id> --device desktop --driver edsl
```

For fixtures, set `device` per variant:

```yaml
variants:
  - name: mobile
    device: iphone
  - name: desktop
    device: desktop
```

Supported built-ins are `desktop`, `iphone`, and `pixel`.

### Sign-In And Authenticated Flows

For multi-step sign-in flows, prefer deterministic `setup_steps` before EDSL
takes over. Setup steps can read credentials from environment variables and
redact sensitive typed values from setup trace events.

Example fixture fragment:

```yaml
env_file: secrets.env
redact_patterns:
  - "test-user-[^\\s]+"
  - "s3cr3t-[^\\s]+"
auth_state:
  save: .uxtest/auth/example-user.json
setup_steps:
  - type: click
    label: Log in
  - type: type
    name: email
    env: TEST_USER_EMAIL
    sensitive: true
  - type: type
    name: password
    env: TEST_USER_PASSWORD
    sensitive: true
  - type: click
    label: Continue
```

To start a later study already signed in, load the saved Playwright storage
state:

```yaml
auth_state:
  load: .uxtest/auth/example-user.json
```

Setup step selectors:

- `selector`: CSS selector
- `name`: input/select name or id
- `placeholder`: input placeholder
- `label`: button/text label

Supported setup step actions:

- `click`
- `type`
- `select`
- `wait`
- `back`
- `scroll`
- `find`

Do not use real user credentials. Use staging/test accounts, static OTPs, or a
test auth bypass. CAPTCHA and live MFA still need a test bypass or a future
manual/hook mechanism.

## Fixture Shape

A typical live-site fixture:

```yaml
id: my-site-discovery
name: My Site Discovery
mode: live-site
comparison_title: My Site Discovery
comparison_output: my-site-discovery.html
url_template: https://example.com/
study_title: My Site Discovery ({variant})
task: >
  Starting from the homepage, decide whether this product is relevant to your
  goal. Find the most useful next item and explain what you would do next.
success_criteria: >
  The visitor identifies relevant evidence and can explain a concrete next
  action.
personas:
  - academic-researcher
runs_per_persona: 1
driver: edsl
max_steps: 8
max_concurrent_runs: 2
keep_runs: 8
analysis_driver: local
eval_policy: report_only
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

Notes for agents:

- Keep `max_concurrent_runs` low for live public sites to avoid bursts from one
  IP.
- Use `keep_runs` to prevent fixture studies from growing without bound.
- Prefer narrow targeted variants when debugging a specific UX question.
- Use `analysis_driver: local` unless you explicitly need model-authored
  analysis. Raw run decisions still use EDSL when `driver: edsl`.

## Important Artifacts

After a run, inspect these first:

```text
.uxtest/comparisons/<comparison>.html
.uxtest/studies/<study-id>/analysis/report.html
.uxtest/studies/<study-id>/analysis/log.html
.uxtest/studies/<study-id>/analysis/uxr_report.html
.uxtest/studies/<study-id>/analysis/findings.json
.uxtest/studies/<study-id>/analysis/scores.json
.uxtest/studies/<study-id>/analysis/animations/index.html
```

Use `log.html` when debugging the system. It shows step-level details,
including EDSL prompts, persona traits, scenarios, remote job metadata, model
answers, screenshots, and action results.

Use `report.html` and `uxr_report.html` when reviewing study findings.

## Writing Narrative Reports

The generated HTML reports are technical evidence reports. When asked for a
narrative report, do not simply summarize `report.html`. Treat the generated
artifacts as source material and write a new report for a reader who wants to
understand the study, the method, the results, and what to do next.

Read these inputs before writing:

```text
.uxtest/studies/<study-id>/study.yaml
.uxtest/studies/<study-id>/analysis/scores.json
.uxtest/studies/<study-id>/analysis/findings.json
.uxtest/studies/<study-id>/analysis/log.html
.uxtest/studies/<study-id>/runs/*/meta.json
.uxtest/studies/<study-id>/runs/*/trace.jsonl
```

For comparison studies, also read:

```text
.uxtest/comparisons/<comparison>.html
```

If the report needs screenshots, reference screenshots from the evidence in
`findings.json` or from trace observations. Do not invent visual evidence.

### Narrative Report Shape

Use this structure unless the user asks for something else:

1. **Title and One-Paragraph Summary**
   State what was tested, for whom, and the most important result.

2. **Context**
   Explain the product/site/page, the visitor jobs being simulated, and why the
   study was run. Keep this concrete. For example: "This study tested whether
   prospective collaborators and students could use the academic homepage to
   identify relevant research and decide on a next action."

3. **Method**
   Explain how `uxtest` ran the study:
   - target URL
   - personas
   - device profiles
   - number of runs
   - max step budget
   - EDSL remote inference for browser decisions
   - Playwright for page interaction and screenshots

   Mention limitations plainly: synthetic users are not human participants,
   EDSL decisions are model outputs, and success detection may need task-specific
   interpretation for exploratory tasks.

4. **What Happened**
   Describe the user journeys in plain language. Use runs and traces as
   evidence:
   - first actions
   - where users navigated
   - what content they found
   - where they stopped, repeated actions, or gave up
   - differences across desktop/mobile/personas

5. **Results**
   Include only the metrics that help the reader:
   - completion counts/rates
   - common outcomes: `done`, `gave_up`, `max_steps`
   - mean steps/frustration when relevant
   - strongest findings

   Do not over-index on synthetic SUS or raw counts if the study is exploratory.

6. **Main Conclusions**
   Turn findings into 3-6 crisp conclusions. Each conclusion should connect
   observed behavior to product/design implications. Example:
   "Visitors expected section navigation on the long homepage. This suggests the
   page would benefit from anchor links or a sticky table of contents."

7. **Recommended Follow-On Steps**
   Separate tool follow-ups from site/product follow-ups:
   - Tool follow-ups: better external-resource handling, task-specific success
     classifiers, richer report synthesis.
   - Site/product follow-ups: navigation, summaries, filters, contact paths,
     clearer CTAs.

8. **Appendix**
   Include study IDs, report paths, run IDs, and links to technical artifacts.

### Narrative Style Rules

- Write for a stakeholder, not for a test harness.
- Lead with what was learned, not with file paths.
- Use concrete evidence from traces, but do not paste large raw JSON blocks.
- Distinguish runtime errors from UX friction.
- Distinguish model/tool limitations from site findings.
- Avoid claiming statistical validity from small synthetic samples.
- Avoid saying "users" without qualification; prefer "synthetic visitors",
  "persona runs", or "agents" when discussing study evidence.
- When a run reached useful evidence but ended as `max_steps`, say that plainly.
- If completion scoring is too strict for an exploratory task, explain that the
  narrative interpretation differs from the raw completion metric.

### Narrative Report Prompt

Use this prompt pattern when asking a coding agent or model to synthesize a
report from artifacts:

```text
Write a narrative UX research report from the uxtest artifacts below.

Audience: product/design/research stakeholders.
Goal: explain the study context, how the synthetic study worked, what happened,
the main conclusions, and recommended next steps.

Use these artifacts as evidence:
- study.yaml
- scores.json
- findings.json
- selected run meta.json files
- selected trace.jsonl events
- report/log paths for appendix

Requirements:
- Do not just summarize the technical report.
- Explain the method in plain language.
- Separate site findings from tool/model limitations.
- Use concrete examples from runs.
- Include completion outcomes, but interpret them cautiously.
- End with prioritized follow-on steps.
```

### Suggested Output Files

When asked to produce narrative reports, write Markdown first:

```text
.uxtest/studies/<study-id>/analysis/narrative_report.md
```

Then compile to HTML or PDF if requested:

```text
.uxtest/studies/<study-id>/analysis/narrative_report.html
.uxtest/studies/<study-id>/analysis/narrative_report.pdf
```

For multi-study comparisons, write:

```text
.uxtest/comparisons/<comparison>-narrative.md
.uxtest/comparisons/<comparison>-narrative.html
.uxtest/comparisons/<comparison>-narrative.pdf
```

## Browser Agent Behavior

The EDSL browser decision schema supports these actions:

- `click`: click a supplied interactive element `ref`.
- `type`: fill an input `ref`.
- `select`: choose an option on a select `ref`.
- `scroll`: scroll down.
- `find`: find and scroll to text or a heading on the page.
- `back`: browser back.
- `wait`: wait briefly.
- `none`: no browser action; often used with `status: done`.

The runner supplies:

- screenshot
- visible viewport text
- visible interactive elements and refs
- visible headings
- recent event history

Important implementation detail: EDSL may ask to click static headings such as
`Research` or `Bio`. The runner now recovers many of those into `find` actions
when the text exists on the page. Treat this as useful UX evidence, not just an
agent mistake: users often expect long academic or marketing pages to have
section navigation.

## Reading Outcomes

Run outcomes are not the same as runtime errors:

- `done`: agent marked the task complete or success criteria were detected.
- `gave_up`: agent gave up or repeated the same action too many times.
- `max_steps`: step budget was exhausted.
- `error`: execution error.
- `interrupted`: stale/incomplete run recovered by the store.

For exploratory studies, `max_steps` and `gave_up` can still contain useful
evidence. Check the trace before concluding the site failed.

The local analyzer classifies common friction:

- static section navigation expectations
- repeated non-navigation
- external content found without task closure
- failed browser actions
- high frustration
- successful task completion

## EDSL Remote Jobs

Each browser step can create an EDSL remote job. A study with 4 personas,
2 device variants, and `max_steps: 8` may create up to 64 remote decision jobs,
plus any model analysis jobs if enabled.

The terminal may print progress URLs such as:

```text
https://www.expectedparrot.com/home/remote-job-progress/<job_uuid>
```

These are expected. Warnings like `Fetching results` or `View partial results`
are progress states unless the command exits non-zero.

To verify whether EDSL was actually used, inspect:

```text
.uxtest/studies/<study-id>/analysis/log.html
```

or grep traces:

```bash
rg -n '"question_type"|"progress_url"|"results_url"' .uxtest/studies/<study-id>/runs
```

## Eval and Regression Checks

Use eval specs to detect known flaws or first-click expectations:

```bash
uv run uxtest eval <study-id> \
  --expect examples/saas_site/expected_flaws.yaml \
  --variant clear \
  --policy threshold
```

Fixtures can include:

```yaml
expected_flaws: expected_flaws.yaml
eval_policy: threshold
minimum_recovered_expected: 1
```

`report_only` is useful for exploratory live-site studies where the goal is
data collection rather than pass/fail gating.

## Report Generation

Analysis writes:

- `findings.json`
- `scores.json`
- `report.html`
- `log.html`
- `study_plan.md`
- `uxr_report.html`
- `human_test_protocol.md`

Regenerate from existing traces:

```bash
uv run uxtest analyze <study-id> --include-interrupted
uv run uxtest uxr <study-id>
```

Regenerate a comparison report programmatically:

```bash
uv run python -c "from uxtest.store import find_store; from uxtest.comparison import write_comparison_report; s=find_store(); print(write_comparison_report(s, title='Comparison', study_ids=['<study-a>', '<study-b>'], output_name='comparison.html'))"
```

## Opening Reports

Opening files on macOS requires a GUI command:

```bash
open .uxtest/comparisons/<report>.html
```

If running in a sandboxed agent environment, request escalation before using
`open`.

## Debugging Checklist

When a study looks wrong:

1. Check command exit code first.
2. Inspect `scores.json` outcomes.
3. Open `log.html` and inspect the last step for each failed run.
4. Distinguish execution errors from UX friction.
5. Check whether the model selected a missing ref or static heading.
6. Check whether repeated clicks did not navigate.
7. Check whether an external site opened and the task should have ended.
8. Consider narrowing the task or reducing `max_steps`.

Useful commands:

```bash
uv run uxtest show <study-id> --json
uv run uxtest show <study-id> <run-id> --trace --json
rg -n '"outcome"|"action_recovery"|"type": "find"|"gave_up"|"max_steps"' .uxtest/studies/<study-id>
```

## Development Checks

Before handing off changes:

```bash
uv run python -m pytest -q tests
```

For narrow changes, prefer focused tests first:

```bash
uv run python -m pytest -q tests/test_runner.py tests/test_store.py
```

Do not delete `.uxtest/studies` artifacts unless explicitly asked. They are
often the evidence the user wants to inspect.
