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

## What To Inspect

Inspect:

- whether known flaws were recovered
- first-click changes across versions
- outcome stability across repeated runs
- whether improvements reduce steps or frustration
- new loops or detours introduced by the change
- screenshots of before/after evidence

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
