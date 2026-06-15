# Report Writer Agent Guide

This guide is for a coding or research agent using `uxtest` evidence to write a
stakeholder-facing UX research report. `uxtest` collects and packages evidence;
the agent writes the narrative, applies judgment, and avoids overclaiming.

## Start Here

Discover this guide from an installed package:

```bash
uxtest docs show report-writer-agent
uxtest docs path report-writer-agent
```

Use these commands to inspect the study evidence:

```bash
uxtest docs show root
uxtest show <study-id> --json
uxtest trace <study-id>
uxtest trace <study-id> --edsl-jobs --json
uxtest batch report <name> --study <study-id-a> --study <study-id-b> --format md,html
```

Read the generated artifacts directly:

```text
.uxtest/studies/<study-id>/study.yaml
.uxtest/studies/<study-id>/analysis/findings.json
.uxtest/studies/<study-id>/analysis/scores.json
.uxtest/studies/<study-id>/analysis/log.html
.uxtest/studies/<study-id>/analysis/report.html
.uxtest/studies/<study-id>/runs/<run-id>/meta.json
.uxtest/studies/<study-id>/runs/<run-id>/trace.jsonl
.uxtest/studies/<study-id>/runs/<run-id>/screenshots/
.uxtest/comparisons/<batch>.md
```

## Role Boundary

Do not write as if `uxtest` itself performed human research. Use precise
language:

- "Synthetic personas" or "browser-agent runs", not "participants" unless the
  study also used humans.
- "The trace shows" or "the model-controlled persona selected", not "users
  definitely will".
- "Evidence suggests" for findings that depend on model behavior.
- "Needs human validation" for high-stakes product, accessibility, legal,
  medical, or financial conclusions.

Your job is to turn evidence into a useful research memo. The tool's job is to
capture browser paths, screenshots, EDSL decisions, action outcomes, stop
quality, deterministic findings, and technical reports.

## Evidence To Extract

For each study, capture:

- Study title, URL, task, and success criteria from `study.yaml`.
- Persona names and traits from run `meta.json`.
- Outcome, final URL, steps taken, and `stop_quality` from `scores.json`.
- Per-step action, thinking, frustration, `action_outcome`, and `stop_signal`
  from `trace.jsonl`.
- Screenshots referenced in trace observations.
- EDSL job URLs from `model_decision.edsl.job`.
- Deterministic findings from `findings.json`.
- Technical context from `log.html` when a claim depends on exact browser state.

Useful trace fields:

```text
action.type
action.text
result.action_outcome
result.final_url
model_decision.thinking
model_decision.edsl.job.results_url
frustration
status
stop_signal.enough_evidence
observation.screenshot
observation.visible_text_preview
```

Interpret `action_outcome` carefully:

- `url_navigation`: the page changed URL path, query, or host.
- `hash_change`: same page with fragment change.
- `new_tab`: a new browser page appeared.
- `menu_opened` or `menu_closed`: same-page interactive state changed.
- `same_page_state_change`: visible text or interactive elements changed.
- `no_visible_change`: strongest candidate for dead click or selector mismatch.

Interpret stop quality carefully:

- `done`: the run stopped successfully.
- `enough_evidence_but_continued`: the agent appeared able to answer the task
  but kept acting.
- `looping`: repeated action or repeated page path.
- `blocked_by_auth`: learning path moved into login or sign-up.
- `blocked_by_no_visible_advance`: final click did not visibly advance.
- `unresolved`: ended without a clearer deterministic class.
- `error`: execution failed.

## Recommended Report Shape

Write the final report as a narrative memo:

1. **Title**
   Name the site/product, study type, and target question.

2. **Context**
   Explain why the study was run and what decision it should inform.

3. **Method**
   State that this was synthetic UX research using model-controlled personas,
   Playwright browser sessions, screenshots, and EDSL remote inference. Include
   run count, persona count, devices, date, and task.

4. **Personas**
   Summarize each persona's role, goal, and evaluative lens.

5. **What Happened**
   Give a concise path narrative by persona or persona group. Include first
   click, notable detours, pages reached, menus opened, and stopping behavior.

6. **Main Findings**
   Three to six findings. Each finding should include:
   - Claim.
   - Evidence from runs/screenshots.
   - Affected personas.
   - Product implication.
   - Confidence level or caveat.

7. **Evidence Walkthrough**
   Link or embed representative screenshots. For each screenshot, explain what
   was visible, what action happened next, and why it matters.

8. **Recommendations**
   Prioritized product or research actions. Separate quick copy/navigation
   fixes from larger product strategy questions.

9. **Follow-On Studies**
   Name the next study type and why it is needed.

10. **Limitations**
    State synthetic sample size, model limitations, possible selector/browser
    artifacts, and whether human validation is needed.

## Citation Style

Use concrete evidence references:

```markdown
In `run-003-startup-founder-d2eb`, step 3, the persona opened Products from the
About page. The trace recorded `action_outcome=menu_opened`, so this was not a
dead click. Screenshot: `runs/run-003-startup-founder-d2eb/screenshots/step-003.png`.
```

When writing Markdown in the same analysis directory, use relative screenshot
paths. When writing a standalone report elsewhere, use paths relative to the
report file or absolute local file links if the user asked for an inspectable
local artifact.

## Quality Bar

Before finalizing, check:

- Every major claim has trace, screenshot, or finding evidence.
- Menu opens and same-page changes are not mislabeled as failed clicks.
- Old runs are not mixed with fresh runs without saying so.
- `max_steps` is not automatically treated as product failure.
- `enough_evidence_but_continued` is treated as a research-agent stop issue,
  not necessarily a site issue.
- EDSL partial jobs or missing screenshots are mentioned if they affect trust.
- Recommendations follow from observed behavior, not from generic best practice.

## Useful Follow-On Commands

```bash
uxtest docs show task-discovery
uxtest docs show conversion-path-testing
uxtest docs show information-architecture
uxtest docs show enterprise-buying-research
uxtest docs show feature-findability
uxtest docs show accessibility-inclusive-ux
uxtest agents export <study-id>
uxtest interview <study-id> --question "What evidence mattered most?"
```

Use study-type docs when the report should recommend a next research task.
