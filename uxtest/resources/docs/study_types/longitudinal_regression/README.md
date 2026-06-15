# Longitudinal Regression

## What This Study Answers

A longitudinal regression study reruns known UX tasks over time to see whether
changes improve, preserve, or regress user experience. It turns earlier
findings into repeatable checks.

Use this study type when you have known flaws, target outcomes, or redesign
hypotheses and want to track them across releases.

## When To Use It

Run this:

- before and after redesigns
- before releases that change navigation, forms, or onboarding
- after fixing a known UX issue
- as a recurring check for critical conversion or product workflows
- when stakeholders need evidence that a change actually improved the path

## Research Questions

1. Did the known flaw recur?
2. Did the intended improvement change behavior?
3. Did the change introduce new detours or confusion?
4. Are outcomes stable across personas and devices?
5. Are technical failures distinct from UX regressions?
6. Which evidence should become a future eval check?

## Recommended Personas

Keep personas stable over time. If you change personas, record why.

Use the smallest set that covers the risk:

- one primary target persona
- one low-confidence or edge-case persona
- one technical or admin persona if the workflow requires it
- one mobile variant when mobile is important

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList`, export a stable subset and version the
reason for any future changes. Longitudinal results are only interpretable when
persona goals and evidence standards stay comparable.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="enterprise-buyer-regression",
            traits={
                "role": "enterprise buyer",
                "tracking_goal": "demo path regression",
                "known_risk": "login or docs mistaken for demo path",
                "evidence_standard": "clear route plus enough confidence",
            },
            instruction=(
                "Use the same demo-evaluation standard on every run. Notice "
                "whether known flaws recur, disappear, or change form."
            ),
        ),
        Agent(
            name="low-confidence-regression",
            traits={
                "role": "low-confidence evaluator",
                "tracking_goal": "CTA and label clarity",
                "known_risk": "ambiguous Get Started or Contact labels",
                "evidence_standard": "plain labels and low hesitation",
            },
            instruction=(
                "Reads labels carefully and hesitates when the next step is "
                "ambiguous. Use the same caution on every run."
            ),
        ),
    ]
)


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")


out_dir = Path(".uxtest/personas")
out_dir.mkdir(parents=True, exist_ok=True)

for agent in agents:
    name = slug(agent.name or agent.traits.get("role", "persona"))
    persona = {
        "schema_version": 1,
        "name": name,
        "description": agent.traits.get("role", name),
        "attributes": dict(agent.traits),
        "accessibility": {},
        "goals_bias": getattr(agent, "instruction", "") or "",
        "frustration": {"threshold": 6, "per_step_decay": 1},
    }
    (out_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(persona, sort_keys=False),
        encoding="utf-8",
    )
```

Then reference the stable persona names:

```yaml
personas:
  - enterprise-buyer-regression
  - low-confidence-regression
```

## Basic Fixture Pattern

```yaml
id: acme-demo-path-regression
name: Acme Demo Path Regression
mode: longitudinal-regression
comparison_title: Acme Demo Path Regression
comparison_output: acme-demo-path-regression.html
url_template: https://www.example.com/
study_title: Acme Demo Path Regression ({variant})
task: >
  Starting from the homepage, find the path to schedule a demo. Continue until
  you reach a demo/contact-sales page or explain why you are blocked.
success_criteria: >
  The visitor reaches a demo/contact-sales path without mistaking login or docs
  for the primary demo path.
personas:
  - enterprise-buyer
runs_per_persona: 2
driver: edsl
max_steps: 8
max_concurrent_runs: 1
keep_runs: 12
analysis_driver: local
expected_flaws: expected_flaws.yaml
eval_policy: report_only
variants:
  - name: current-desktop
    device: desktop
  - name: current-mobile
    device: iphone
```

Save this as:

```text
examples/<site_or_product>/longitudinal-regression.yaml
```

## Expected Flaws

Use an expected-flaw file to track whether known problems appear again.

```yaml
flaws:
  - id: login_mistaken_for_demo
    description: Visitor mistakes login or dashboard entry for demo/signup.
    evidence:
      text_any:
        - login
        - dashboard
      outcome_any:
        - gave_up
        - max_steps

  - id: pricing_not_findable
    description: Visitor looks for pricing but cannot find plan or quote path.
    evidence:
      text_any:
        - pricing
        - quote
        - contact sales
```

Use flaws to guide review, not to replace human interpretation. A known flaw can
reappear in a new form.

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/longitudinal-regression.yaml
```

Open:

```text
.uxtest/comparisons/acme-demo-path-regression.html
```

Then inspect:

```text
.uxtest/studies/<study-id>/analysis/log.html
```

Keep fixture IDs stable for the same recurring study. Use new IDs only when the
research question changes enough that old and new runs should not be compared.

## What To Inspect

Inspect:

- whether known flaws were recovered
- first-click changes across versions
- outcome stability across repeated runs
- whether improvements reduce steps or frustration
- new loops or detours introduced by the change
- screenshots of before/after evidence

## How To Interpret Results

Longitudinal regression translates research findings into a repeatable evidence
loop. It should answer what changed, not just whether a check passed.

Read across runs for:

1. **Known flaw status**
   Did the flaw recur, reduce, resolve, or appear under a new label?

2. **Behavioral change**
   Did first clicks, detours, hesitation, or confidence change?

3. **Persona stability**
   Did the improvement help all tracked personas or only the target persona?

4. **Device stability**
   Did desktop improve while mobile stayed broken, or vice versa?

5. **New risk**
   Did the fix create a different confusion, trust gap, or routing problem?

6. **Check maturity**
   Which qualitative finding is now stable enough to become a stricter eval
   check?

Separate runtime failures from UX regressions. Use screenshots and `log.html`
before interpreting a failed run as a product issue.

## Running Over Time

Keep fixture IDs stable when tracking the same study. Use `keep_runs` to retain
recent evidence without growing indefinitely.

For a major redesign, use variants such as `before`, `after`, or environment
URLs:

```yaml
variants:
  - name: production-before
    url: https://www.example.com/
  - name: staging-after
    url: https://staging.example.com/
```

## Common Findings

- A fix improves desktop but not mobile.
- The original issue is fixed, but a new detour appears.
- Copy changes improve first-click behavior but reduce credibility.
- A path is shorter but less clear.
- Known flaws disappear for target personas but remain for edge personas.
- Runtime instability is mistaken for UX regression unless logs are inspected.

## Narrative Report Shape

1. Summary: whether the release improved, preserved, or regressed behavior.
2. Context: known issue and design/product change.
3. Method: stable fixture, personas, devices, and comparison period.
4. Before/after behavior: paths, outcomes, screenshots, and friction.
5. Known flaw status: recovered, reduced, resolved, or changed form.
6. New risks: regressions or unintended side effects.
7. Follow-on steps: fixes, stricter eval checks, and future run cadence.

## Example Narrative Summary

Use a style like this:

```text
This longitudinal regression study reran the demo-path task after the navigation
and CTA changes. The original flaw, where buyers mistook login for the demo
path, did not recur on desktop. Mobile improved less: the buyer still opened
the collapsed menu twice before finding the right route. The redesign shortened
the path, but it also moved customer proof farther from the CTA, which reduced
confidence for the low-confidence persona. The next step is to preserve the
clearer demo label while restoring nearby proof, then promote the login
confusion pattern from expected flaw to a stricter regression check.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to compare before/after
screenshots or confirm that a known issue is fixed:

```bash
uv run uxtest humanize-export <study-id> \
  --template longitudinal-regression \
  --screenshots representative \
  --max-screenshots 8
```

Review and launch:

```bash
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- Which version makes the next step clearer?
- Does the known issue still appear in this screenshot?
- What new confusion, if any, did the change introduce?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Longitudinal regression usually leads to:

- Stricter eval checks for stable, well-understood issues.
- New task discovery or content comprehension when a redesign changes the page
  purpose.
- Conversion path testing when a recurring study exposes a specific target-path
  problem.
- Human validation when the regression affects high-stakes product or brand
  decisions.
