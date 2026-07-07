# uxtest Agent Guide

`uxtest` runs synthetic-user UX studies against live web pages with Playwright
and EDSL remote inference. This README is written for coding agents that have
installed the package and need to discover the docs, copy examples, run studies,
and inspect evidence from a terminal.

## Agent Start Here

If the package is not already installed, install it from the public repository:

```bash
pip install git+https://github.com/expectedparrot/uxtest.git
python -m playwright install chromium
```

When `uxtest` is published to PyPI, the install command can become
`pip install uxtest`.

After installing `uxtest`, do not assume you have the source repository. Use the
built-in documentation commands first:

```bash
uxtest doctor
uxtest --version
uxtest docs
uxtest docs list
uxtest docs show root
uxtest examples list
uxtest figma doctor
```

Use `docs show` when you need instructions in the current terminal context:

```bash
uxtest docs show task-discovery
uxtest docs show report-writer-agent
uxtest docs show conversion-path-testing
uxtest docs show information-architecture
uxtest docs show study-types
uxtest docs show spec
```

Use `docs path` when another tool needs a filesystem path:

```bash
uxtest docs path root
uxtest docs path task-discovery
```

Use `examples path` when you only need to inspect a bundled fixture:

```bash
uxtest examples path expectedparrot-enterprise-demo
uxtest examples path saas-regression-edsl
```

Use `examples copy` before editing or running a bundled example as a project
artifact:

```bash
uxtest examples copy ./uxtest-examples
uxtest examples copy ./enterprise-demo.yaml --name expectedparrot-enterprise-demo
uxtest examples copy ./task-discovery-guide --name task-discovery
```

`docs open` exists for local interactive use, but sandboxed agents may need
permission before launching GUI apps:

```bash
uxtest docs open root
```

## Capability Map

Use this map when deciding what kind of research study to run:

- **First impression and orientation**: use `task-discovery` to learn what
  visitors think a page is for, what they click first, what they misunderstand,
  and where they hesitate.
- **Message and content interpretation**: use `content-comprehension` to learn
  whether visitors can explain the offer, audience, claims, jargon, proof, and
  next step.
- **Target-action paths**: use `conversion-path-testing` to study demo, signup,
  pricing, checkout, contact-sales, lead form, or gated-asset paths.
- **Findability and navigation**: use `information-architecture` to study where
  visitors expect content such as docs, security, pricing, examples, support,
  API references, or case studies to live.
- **Feature or capability proof**: use `feature-findability` to learn whether
  visitors can determine if a product supports a feature, integration,
  workflow, API, export, permission model, or use case.
- **Enterprise evaluation**: use `enterprise-buying-research` to study whether
  buyers, technical evaluators, risk reviewers, and operators can find enough
  product, proof, security, implementation, and commercial evidence to continue.
- **Competitive or variant comparison**: use `competitive-benchmark-studies` to
  compare the same task across competitors, variants, staging/production, or
  before/after designs.
- **First-run product activation**: use `onboarding-activation` to study whether
  newly invited or signed-up users can reach a first meaningful action.
- **Authenticated product workflows**: use `post-login-workflow-testing` for
  role-specific logged-in tasks such as inviting users, configuring
  integrations, exporting reports, or changing settings.
- **Inclusive UX risk discovery**: use `accessibility-inclusive-ux` to locate
  risks for mobile-only, low-confidence, plain-language, low-vision,
  keyboard-oriented, or unfamiliar-domain users. This complements, but does not
  replace, formal accessibility testing.
- **Tracking fixes over time**: use `longitudinal-regression` to rerun known UX
  tasks, expected flaws, and redesign hypotheses across releases.

Each study guide includes an EDSL `AgentList` persona export pattern, fixture
template, run command, `log.html` inspection workflow, narrative report shape,
human screenshot validation guidance, and follow-on studies.

## Which Doc To Read

Choose the smallest doc that matches the task:

- `root`: this operational agent guide.
- `report-writer-agent`: instructions for a research/coding agent that needs to
  turn `uxtest` evidence into a narrative stakeholder report.
- `task-discovery`: fully worked study guide for first-impression and first-click
  discovery studies.
- `conversion-path-testing`: demo, signup, pricing, checkout, contact, or other
  target-action paths.
- `information-architecture`: expected content findability across nav, menus,
  search/find behavior, and mobile.
- `enterprise-buying-research`: enterprise trust, proof, technical, risk, and
  commercial evidence.
- `competitive-benchmark-studies`: same-task comparison across competitors,
  variants, or before/after designs.
- `content-comprehension`: messaging, audience, value proposition, jargon,
  claims, and next-step interpretation.
- `feature-findability`: feature, integration, workflow, or use-case evidence.
- `onboarding-activation`: first-run setup and first meaningful product action.
- `post-login-workflow-testing`: authenticated role-specific product workflows.
- `accessibility-inclusive-ux`: constrained personas and device/access needs.
- `longitudinal-regression`: repeated tasks, known flaws, and release
  regression checks.
- `study-types`: index of UXR study patterns bundled with the package.
- `spec`: implementation and architecture notes.

Choose examples by alias:

- `expectedparrot`: all Expected Parrot live-site fixtures.
- `expectedparrot-task-discovery`: first-impression and first-click fixture.
- `expectedparrot-content-comprehension`: homepage comprehension fixture.
- `expectedparrot-conversion-path`: demo/contact next-step fixture.
- `expectedparrot-information-architecture`: docs, product, company, and
  resource findability fixture.
- `expectedparrot-feature-findability`: EDSL/programmatic workflow evidence
  fixture.
- `expectedparrot-enterprise-demo`: live-site fixture for enterprise demo intent.
- `expectedparrot-credibility`: live-site fixture for credibility and seriousness.
- `jjh-discovery`: live-site fixture for homepage discovery.
- `jjh-targeted`: targeted live-site fixture.
- `saas-regression`: deterministic local SaaS fixture.
- `saas-regression-edsl`: EDSL-backed local SaaS fixture.
- `task-discovery`: the task discovery guide as an example resource.

If an alias is not enough, run:

```bash
uxtest docs list
uxtest examples list
```

Then pass any listed relative path to `docs show`, `docs path`, `examples path`,
or `examples copy`.

## Environment

From a source checkout, use `uv run`:

```bash
uv sync
uv run uxtest --help
uv run python -m pytest -q tests
```

From an installed package, call `uxtest` directly unless your environment
requires a wrapper:

```bash
uxtest --help
uxtest doctor
```

EDSL is a normal PyPI dependency. Do not depend on a local EDSL checkout path.
Remote inference credentials are expected in `.env` or the environment. Normal
browser runs use EDSL remote inference and should not require a local OpenAI API
key.

`uxtest doctor` checks that `uxtest` is importable, EDSL is importable,
Playwright Chromium can launch, and pandoc is available for HTML/PDF narrative
reports. If Playwright browsers are missing, run:

```bash
python -m playwright install chromium
```

## Operating Model

`uxtest` stores state under `uxtest_store/` in the current project:

- `uxtest_store/personas/*.yaml`: reusable persona templates.
- `uxtest_store/studies/<study-id>/study.yaml`: study definition.
- `uxtest_store/studies/<study-id>/runs/<run-id>/`: raw traces, screenshots, and run
  metadata.
- `uxtest_store/studies/<study-id>/analysis/`: generated reports and summaries.
- `uxtest_store/comparisons/*.html`: multi-study comparison reports.

Raw run traces are the source of truth. Reports are derived and can be
regenerated.

## Run A Bundled Fixture

Copy a fixture into your workspace before editing it:

```bash
uxtest examples copy ./enterprise-demo.yaml --name expectedparrot-enterprise-demo
uxtest ci ./enterprise-demo.yaml
```

From a source checkout, existing source-tree examples can also be run directly:

```bash
uv run uxtest ci examples/saas_site/regression-edsl.yaml
uv run uxtest ci examples/jjh_site/discovery.yaml
uv run uxtest ci examples/jjh_site/targeted.yaml
```

The fixture runner will:

1. Create or update personas.
2. Create or update fixture-backed studies.
3. Launch Playwright browser runs.
4. Ask EDSL for browser decisions at each step when `driver: edsl`.
5. Analyze the runs.
6. Generate reports, animations, eval outputs, and comparison HTML when
   configured.

For public live sites, keep `max_concurrent_runs` low to avoid request bursts
from one IP.

## Create A One-Off Study

Use this when no fixture exists:

```bash
uxtest study new "Homepage discovery" \
  --url "https://example.com/" \
  --task "Starting from the homepage, decide what you would click next and why." \
  --success-criteria "The visitor identifies a relevant next action." \
  --persona academic-researcher \
  --runs-per-persona 1
```

Then run and analyze:

```bash
uxtest study run <study-id> --driver edsl --max-steps 8 --max-concurrent-runs 2
uxtest analyze <study-id> --include-interrupted
uxtest animate <study-id>
uxtest uxr <study-id>
```

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
overrides:
  model: gpt-4o
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

Built-in devices are `desktop`, `iphone`, and `pixel`.

## Authenticated Flows

For sign-in and multi-step setup, use deterministic `setup_steps` before EDSL
takes over. Setup values can come from environment variables and sensitive typed
values are redacted from setup traces.

```yaml
env_file: secrets.env
redact_patterns:
  - "test-user-[^\\s]+"
  - "s3cr3t-[^\\s]+"
auth_state:
  save: uxtest_store/auth/example-user.json
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

Load saved Playwright storage state in later studies:

```yaml
auth_state:
  load: uxtest_store/auth/example-user.json
```

Supported setup actions are `click`, `type`, `select`, `wait`, `back`, `scroll`,
and `find`. Supported selectors include `selector`, `name`, `placeholder`, and
`label`.

Do not use real user credentials. Use staging accounts, static test OTPs, or a
test auth bypass. CAPTCHA and live MFA need a test bypass or manual hook.

## Evidence To Inspect

After a run, inspect these first:

```text
uxtest_store/comparisons/<comparison>.html
uxtest_store/studies/<study-id>/analysis/report.html
uxtest_store/studies/<study-id>/analysis/log.html
uxtest_store/studies/<study-id>/analysis/uxr_report.html
uxtest_store/studies/<study-id>/analysis/findings.json
uxtest_store/studies/<study-id>/analysis/scores.json
uxtest_store/studies/<study-id>/analysis/animations/index.html
```

Use `log.html` to debug the system. It shows step-level details: persona,
scenario, screenshots, EDSL prompts, remote job metadata, model answers, and
browser action results.

Use `report.html`, `uxr_report.html`, and comparison reports to review findings.

Use raw traces when the reports look wrong:

```bash
uxtest show <study-id> --json
uxtest show <study-id> <run-id> --trace --json
uxtest trace <study-id>
uxtest trace <study-id> --edsl-jobs
rg -n '"outcome"|"action_recovery"|"type": "find"|"gave_up"|"max_steps"' uxtest_store/studies/<study-id>
rg -n '"action_outcome"|"no_visible_change"|"menu_opened"|"same_page_state_change"' uxtest_store/studies/<study-id>
rg -n '"stop_signal"|"stop_quality"|"enough_evidence_but_continued"|"blocked_by_auth"' uxtest_store/studies/<study-id>
```

Generate a narrative report when the user wants a stakeholder-readable summary
instead of the technical evidence report:

```bash
uxtest report <study-id>
uxtest report <study-id> --format html
uxtest report <study-id> --format md,html,pdf
```

The report command reads existing traces, screenshots, findings, and scores. It
writes `analysis/narrative_report.md` by default and uses pandoc for HTML/PDF.

When a coding or research agent is writing the final narrative itself, read the
packaged report-writing guide first:

```bash
uxtest docs show report-writer-agent
```

That guide explains which artifacts to inspect, how to cite screenshots and
traces, how to use `action_outcome` and `stop_quality`, and how to avoid
overclaiming from synthetic browser-agent evidence.

## Batch Research Reports

Use `batch report` when several study reports need to become one cross-study
research synthesis. This command reads existing `scores.json`, `findings.json`,
run metadata, traces, screenshots, and logs. It deduplicates recurring findings,
summarizes outcomes, flags trace-quality signals such as clicks with no visible
advance, links source reports, and writes a narrative Markdown report. New
traces classify each browser action as `url_navigation`, `hash_change`,
`new_tab`, `menu_opened`, `same_page_state_change`, `scroll`,
`no_visible_change`, or a related outcome so agents do not treat all
non-navigation clicks as failures.

Batch reports also classify run resolution quality. Use `stop_quality` in
`scores.json` and the "Run Resolution" section to distinguish `done`,
`enough_evidence_but_continued`, `looping`, `blocked_by_auth`,
`blocked_by_no_visible_advance`, `unresolved`, and `error`. New traces include
per-step `stop_signal` hints when the browser agent appears to have enough
evidence to answer an exploratory task but has not stopped yet.

```bash
uxtest batch report expectedparrot-cross-study \
  --title "Expected Parrot Cross-Study Report" \
  --study <study-id-a> \
  --study <study-id-b> \
  --comparison uxtest_store/comparisons/<comparison-a>.html \
  --format md,html,pdf
```

Use `batch run` when you have a YAML manifest listing fixture files and want to
run them before generating the synthesis:

```yaml
id: expectedparrot-cross-study
title: Expected Parrot Cross-Study Report
formats: [md, html, pdf]
fixtures:
  - examples/expectedparrot_site/task-discovery.yaml
  - examples/expectedparrot_site/content-comprehension.yaml
  - examples/expectedparrot_site/conversion-path.yaml
```

Run it:

```bash
uxtest batch run expectedparrot-batch.yaml
```

Batch reports are written to `uxtest_store/comparisons/` by default:

```text
uxtest_store/comparisons/<name>.md
uxtest_store/comparisons/<name>.html
uxtest_store/comparisons/<name>.pdf
uxtest_store/comparisons/<name>.manifest.json
```

## Figma Design Studies

Use `figma` commands when the target is a Figma design or prototype rather than
a live web page. There are two workflows:

- Static design frames: import Figma image exports and ask EDSL vision models
  what a persona understands or would click next.
- Clickable prototypes: audit Figma metadata for visible labels versus wired
  interactions, then generate a Playwright runner that opens the shared
  prototype URL, captures screenshots, asks EDSL for the next action, and
  records a step trace.

Set a Figma access token before importing:

```bash
export FIGMA_ACCESS_TOKEN=...
uxtest figma doctor
```

Static frame imports require `FIGMA_ACCESS_TOKEN`. Prototype runners can run
without the Figma API, but prototype audits and high-quality prototype runners
use Figma metadata when `FIGMA_ACCESS_TOKEN` is set. Metadata is cached under
`uxtest_store/figma/cache/`; if Figma returns `429`, uxtest uses stale cached
metadata when available and records the rate-limit details.

Import a selected frame from a copied Figma selection URL:

```bash
uxtest figma import "https://www.figma.com/design/<file-key>/<name>?node-id=<node>"
```

If the URL is a whole file rather than a selected frame, import top-level frames:

```bash
uxtest figma import "https://www.figma.com/design/<file-key>/<name>" --frames top-level --limit 12
```

The command writes a local design evidence bundle:

```text
uxtest_store/figma/<import-id>/manifest.json
uxtest_store/figma/<import-id>/frames/*.png
```

Generate an EDSL vision study script from an import:

```bash
uxtest figma study <import-id> \
  --task "Can an enterprise visitor figure out what to click to schedule a demo?"
```

Or import and generate the script in one step:

```bash
uxtest figma study "https://www.figma.com/design/<file-key>/<name>?node-id=<node>" \
  --task "What would a new visitor click first?"
```

The generated script is dry-run by default:

```bash
python uxtest_store/figma/<import-id>/figma_vision_study.py
```

Run it with EDSL remote inference:

```bash
python uxtest_store/figma/<import-id>/figma_vision_study.py --launch
```

Audit a clickable prototype before asking an agent to navigate it:

```bash
uxtest figma audit "https://www.figma.com/proto/<file-key>/<name>?node-id=<node>"
```

The audit writes:

```text
uxtest_store/figma/audit-<file-key>-<node>/audit.json
uxtest_store/figma/audit-<file-key>-<node>/audit.md
```

Use the audit to identify visible labels that are not wired as prototype
interactions, vague interaction labels, and likely dead-end affordances. For
agents, this is the first command to run against a prototype because Figma
renders much of the experience as canvas content; Playwright cannot reliably
query visible labels from the DOM.

Generate a clickable prototype runner from a `/proto/` URL:

```bash
uxtest figma prototype "https://www.figma.com/proto/<file-key>/<name>?node-id=<node>" \
  --task "Can an enterprise visitor understand the product and find the demo path?" \
  --max-steps 8
```

The generated runner is dry-run by default:

```bash
python uxtest_store/figma/<prototype-id>/figma_prototype_runner.py
```

Launch the browser and EDSL coordinate-click loop:

```bash
python uxtest_store/figma/<prototype-id>/figma_prototype_runner.py --launch
```

The runner records `failure_type` values such as `unwired_visible_affordance`,
`repeated_no_op`, `coordinate_miss`, and `agent_invalid_decision`. When Figma
interaction metadata is available, the runner gives EDSL exact candidate
interaction centers and snaps matching decisions to those centers before
clicking.

Use `--headed` when Figma requires browser login or when you need to inspect
prototype behavior manually:

```bash
python uxtest_store/figma/<prototype-id>/figma_prototype_runner.py --launch --headed
```

Write a Markdown report of imported frames or a prototype run trace:

```bash
uxtest figma report <import-id>
uxtest figma report <prototype-id>
```

Use this workflow for design-stage questions:

- What does a persona think this screen is for?
- What would they click first?
- Which labels, CTAs, or visual hierarchy are confusing?
- Does the frame communicate credibility or enterprise readiness?
- Where does a clickable prototype route a persona, and where does the flow
  become blocked?
- How does the design intent compare to the later live site?

## Export A Human Screenshot Survey

Use `humanize-export` when you want to validate synthetic findings with human
respondents through EDSL `humanize()`. The exporter does not record human
browser sessions. It turns selected `uxtest` screenshots into an EDSL survey
script that humans can answer.

```bash
uxtest humanize-export <study-id> \
  --template task-discovery \
  --screenshots representative \
  --max-screenshots 8
```

The command writes:

```text
uxtest_store/studies/<study-id>/analysis/humanize_survey.py
uxtest_store/studies/<study-id>/analysis/humanize_survey.manifest.json
```

The generated script is safe by default:

```bash
python uxtest_store/studies/<study-id>/analysis/humanize_survey.py
```

It prints the study and scenario count without launching anything. To create
the human survey on Expected Parrot, run:

```bash
python uxtest_store/studies/<study-id>/analysis/humanize_survey.py --launch
```

The generated script uses EDSL's `humanize_schema` to control human-survey
presentation. In the script, look for:

```python
HUMANIZE_SCHEMA = {
    "survey": {
        "custom_css": "..."
    }
}
```

When `--launch` is used, the script passes that schema to EDSL:

```python
survey.by(scenarios).humanize(
    human_survey_name=args.name,
    scenario_list_method="ordered",
    survey_visibility=args.visibility,
    humanize_schema=HUMANIZE_SCHEMA,
)
```

The default exporter CSS constrains screenshots so they do not dominate the
survey page:

```css
img {
  display: block;
  width: auto !important;
  max-width: min(100%, 760px) !important;
  max-height: 70vh !important;
  height: auto !important;
  object-fit: contain !important;
}
```

Edit `HUMANIZE_SCHEMA["survey"]["custom_css"]` in the generated script before
launching if you need smaller screenshots, different borders, tighter spacing,
or other survey-level styling. This is the right place for presentation changes;
do not resize the original trace screenshots unless you specifically need lower
resolution evidence files.

Available templates:

- `task-discovery`: what is this page for, what would you click next, and how
  confident are you?
- `credibility`: what evidence makes the company/product credible, what proof
  is missing, and how confident are you?
- `conversion`: what is the next action, what blocks conversion, and how clear
  is the path?
- `comprehension`: what does the content say, what is confusing, and how
  confident is the reader?

Screenshot selection modes:

- `representative`: first, highest-frustration, and last screenshot per run,
  deduped up to `--max-screenshots`.
- `first`: first screenshot per run.
- `last`: last screenshot per run.
- `first-last`: first and last screenshot per run.
- `high-frustration` or `confusing`: highest-frustration screenshot per run.
- `all`: every trace screenshot, capped by `--max-screenshots`.

Use the manifest to see exactly which run, persona, step, URL, synthetic action,
and screenshot were exported. After collecting human responses with EDSL, an
agent can compare human stated interpretations and intended clicks against the
synthetic browser traces.

## Generate Saliency Overlays

Use `saliency run` when you want visual-attention evidence for screenshots from
a completed study. This is useful for questions about whether CTAs, trust
signals, forms, or navigation are likely to attract attention before the
synthetic visitor acts.

`uxtest` does not fabricate saliency maps. This command requires a real
external saliency model command. If no command is configured, it fails.

The command writes:

```text
uxtest_store/studies/<study-id>/analysis/saliency/manifest.json
uxtest_store/studies/<study-id>/analysis/saliency/index.html
uxtest_store/studies/<study-id>/analysis/saliency/*-overlay.png
uxtest_store/studies/<study-id>/analysis/saliency/*-map.png
```

Use SUM by wrapping its inference command:

```bash
export UXTEST_SUM_DIR=/path/to/SUM
uxtest saliency run <study-id> --sum \
  --screenshots representative \
  --max-screenshots 12
```

The `--sum` shorthand runs a command shaped like:

```bash
python $UXTEST_SUM_DIR/inference.py \
  --img_path {input} \
  --condition 3 \
  --output_path {output_dir} \
  --saliency_map_type Overlay
```

If your SUM checkout or another saliency model needs a different invocation,
use `--engine command`:

```bash
uxtest saliency run <study-id> \
  --engine command \
  --command-template "python /path/to/inference.py --img_path {input} --output_path {output_dir} --condition 3 --saliency_map_type Overlay"
```

Supported placeholders are:

- `{input}`: source screenshot path.
- `{output}`: preferred overlay output path.
- `{map}`: preferred raw saliency-map output path.
- `{output_dir}`: per-screenshot working output directory.
- `{scenario_id}`: stable screenshot scenario id.

If the command does not write `{output}`, `uxtest` copies the newest image from
`{output_dir}` as the overlay. The manifest records the exact command,
return code, stdout, stderr, screenshot, overlay, persona, run, step, and
synthetic action.

## Export Rich EDSL Trace Agents

Use `agents export` when you want downstream EDSL jobs or coding agents to work
from completed browser sessions instead of re-reading raw trace JSON. The export
creates one EDSL `Agent` per run. Each agent includes the original persona,
study task, outcome, final URL, step-by-step journey, visible text snippets,
actions, thinking, frustration scores, and screenshot references.

```bash
uxtest agents export <study-id>
```

The command writes:

```text
uxtest_store/studies/<study-id>/analysis/agent_list.py
uxtest_store/studies/<study-id>/analysis/agent_list.manifest.json
```

Inspect the generated list without launching inference:

```bash
python uxtest_store/studies/<study-id>/analysis/agent_list.py
```

Inside the generated script, call `build_agent_list()` to get an EDSL
`AgentList`. Screenshot paths are also materialized as EDSL `FileStore` objects
under each agent's `screenshot_files` trait, so vision-capable EDSL jobs can
inspect the same screens the browser agent saw.

Use `interview` when you want EDSL to ask follow-up questions of those rich
trace agents:

```bash
uxtest interview <study-id> \
  --question "What evidence made the company feel serious or not serious?" \
  --question "What would you need before scheduling a demo?"
```

The command writes:

```text
uxtest_store/studies/<study-id>/analysis/agent_interview.py
uxtest_store/studies/<study-id>/analysis/agent_interview.manifest.json
```

Dry-run first:

```bash
python uxtest_store/studies/<study-id>/analysis/agent_interview.py
```

Launch remote EDSL inference only when ready:

```bash
python uxtest_store/studies/<study-id>/analysis/agent_interview.py --launch
```

This pattern is useful for post-study synthesis questions such as:

- What did each synthetic visitor believe after the first screen?
- Which proof points were actually seen before conversion?
- Which screenshots should be quoted in a narrative report?
- Where do persona groups disagree about credibility, clarity, or risk?

## EDSL Remote Jobs

Each browser step can create an EDSL remote job. A study with 4 personas,
2 device variants, and `max_steps: 8` may create up to 64 remote decision jobs,
plus model-analysis jobs if enabled.

Remote job progress URLs such as the following are expected:

```text
https://www.expectedparrot.com/home/remote-job-progress/<job_uuid>
```

To verify that EDSL was used, inspect `log.html` or grep traces:

```bash
uxtest trace <study-id> --edsl-jobs
rg -n '"question_type"|"progress_url"|"results_url"' uxtest_store/studies/<study-id>/runs
```

## Browser Agent Behavior

The EDSL browser decision schema supports:

- `click`: click a supplied interactive element ref.
- `type`: fill an input ref.
- `select`: choose an option on a select ref.
- `scroll`: scroll down.
- `find`: find and scroll to text or a heading on the page.
- `back`: go back.
- `wait`: wait briefly.
- `none`: no browser action, often with `status: done`.

The runner supplies screenshot, visible text, visible interactive elements,
visible headings, and recent event history.

If EDSL asks to click static headings such as `Research` or `Bio`, the runner
can recover many of those requests into `find` actions when the text exists.
Treat this as UX evidence: synthetic visitors may be expecting section
navigation.

## Reading Outcomes

Run outcomes are not the same as runtime errors:

- `done`: agent marked the task complete or success criteria were detected.
- `gave_up`: agent gave up or repeated the same action too many times.
- `max_steps`: step budget was exhausted.
- `error`: execution error.
- `interrupted`: stale or incomplete run recovered by the store.

For exploratory studies, `max_steps` and `gave_up` can still contain useful
evidence. Check traces before concluding the site failed.

## Narrative Reports

Technical reports are evidence reports. When asked for a narrative report, read
the generated artifacts and write a new stakeholder-facing report.

Read at least:

```text
uxtest_store/studies/<study-id>/study.yaml
uxtest_store/studies/<study-id>/analysis/scores.json
uxtest_store/studies/<study-id>/analysis/findings.json
uxtest_store/studies/<study-id>/analysis/log.html
uxtest_store/studies/<study-id>/runs/*/meta.json
uxtest_store/studies/<study-id>/runs/*/trace.jsonl
```

For comparison studies, also read:

```text
uxtest_store/comparisons/<comparison>.html
```

Write Markdown first:

```text
uxtest_store/studies/<study-id>/analysis/narrative_report.md
```

Then compile to HTML or PDF if requested.

Use this structure unless the user asks otherwise:

1. Title and one-paragraph summary.
2. Context: product, page, audience, and reason for study.
3. Method: personas, devices, runs, max step budget, Playwright, and EDSL remote
   inference.
4. What happened: user journeys, first clicks, navigation paths, confusion, and
   stopping points.
5. Results: completion outcomes, common failure modes, and strongest findings.
6. Main conclusions: 3-6 implications tied to observed behavior.
7. Follow-on steps: separate product/site work from tool/model limitations.
8. Appendix: study IDs, run IDs, and artifact paths.

Style rules:

- Write for stakeholders, not a test harness.
- Lead with what was learned.
- Distinguish UX friction from runtime errors.
- Distinguish site findings from model/tool limitations.
- Do not claim statistical validity from small synthetic samples.
- Prefer "synthetic visitors", "persona runs", or "agents" when discussing
  evidence.
- Do not invent visual evidence; use screenshots from traces or findings.

## Eval And Regression Checks

Use eval specs to detect known flaws or expected first-click behavior:

```bash
uxtest eval <study-id> \
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

Use `report_only` for exploratory live-site studies where the goal is evidence
collection rather than pass/fail gating.

## Report Regeneration

Regenerate reports from existing traces:

```bash
uxtest analyze <study-id> --include-interrupted
uxtest uxr <study-id>
```

Analysis writes:

- `findings.json`
- `scores.json`
- `report.html`
- `log.html`
- `study_plan.md`
- `uxr_report.html`
- `human_test_protocol.md`

## Debugging Checklist

When a study looks wrong:

1. Check the command exit code.
2. Inspect `scores.json` outcomes.
3. Open `log.html` and inspect the last step for failed runs.
4. Distinguish execution errors from UX friction.
5. Check whether the model selected a missing ref or static heading.
6. Check whether repeated clicks did not navigate.
7. Check whether an external site opened and the task should have ended.
8. Narrow the task or reduce `max_steps` if the agent is wandering.

Opening files on macOS requires a GUI command:

```bash
open uxtest_store/comparisons/<report>.html
```

Sandboxed agents may need approval before running `open`.

## Development Checks

Before handing off package changes:

```bash
uv run python -m pytest -q tests
uv build
```

Do not delete `uxtest_store/studies` unless explicitly asked. Those artifacts are
often the evidence the user wants to inspect.
