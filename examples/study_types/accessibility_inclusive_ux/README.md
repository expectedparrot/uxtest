# Accessibility Inclusive UX

## What This Study Answers

An accessibility inclusive UX study asks how well a task works for visitors with
different access needs, device constraints, confidence levels, language
preferences, or domain familiarity. It does not replace formal accessibility
audits, screen-reader testing, or WCAG checks. It complements them by showing
where synthetic visitors with specific constraints hesitate, misunderstand, or
fail to complete a task.

Use this study type to test:

- mobile-only use
- low-vision or zoomed layouts
- low-confidence visitors
- plain-language comprehension
- keyboard-oriented expectations
- small-screen form completion
- unfamiliar-domain visitors

## When To Use It

Run this when a workflow must work for a broad audience, when support receives
confusion reports, or when a design relies heavily on visual hierarchy, small
text, dense forms, hidden menus, or jargon.

## Research Questions

1. Can constrained visitors identify the next action?
2. Does layout or device size hide important controls?
3. Are labels plain enough for low-domain-familiarity visitors?
4. Do forms, errors, and confirmations explain recovery?
5. Does the task require precision, memory, or interpretation that creates
   friction?
6. Which issues should be escalated to formal accessibility testing?

## Recommended Personas

Use constraint-specific personas:

- `mobile-only-user`: uses a small touch device and avoids desktop assumptions
- `low-confidence-user`: reads carefully and hesitates when labels are vague
- `plain-language-reader`: prefers simple terms and concrete examples
- `low-vision-zoom-user`: needs large targets and clear visual hierarchy
- `keyboard-oriented-user`: expects predictable focus and form order
- `domain-newcomer`: understands general web patterns but not domain jargon

These personas are approximations. Treat findings as risk indicators, not proof
of accessibility compliance.

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList`, export personas that encode the access
constraint, confidence level, domain familiarity, and device context being
studied.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="mobile-only-user",
            traits={
                "access_context": "small touch device",
                "device": "mobile",
                "confidence": "medium",
                "domain_familiarity": "medium",
            },
            instruction=(
                "Uses mobile-first expectations, notices hidden menus, small "
                "targets, cramped forms, and controls that require desktop "
                "assumptions."
            ),
        ),
        Agent(
            name="plain-language-reader",
            traits={
                "access_context": "plain-language preference",
                "device": "desktop",
                "confidence": "low",
                "domain_familiarity": "low",
            },
            instruction=(
                "Needs concrete labels and simple explanations. Hesitates when "
                "copy uses jargon, acronyms, or abstract claims."
            ),
        ),
    ]
)


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")


out_dir = Path("uxtest_store/personas")
out_dir.mkdir(parents=True, exist_ok=True)

for agent in agents:
    name = slug(agent.name or agent.traits.get("access_context", "persona"))
    persona = {
        "schema_version": 1,
        "name": name,
        "description": agent.traits.get("access_context", name),
        "attributes": dict(agent.traits),
        "accessibility": {
            "context": agent.traits.get("access_context", ""),
            "device": agent.traits.get("device", ""),
        },
        "goals_bias": getattr(agent, "instruction", "") or "",
        "frustration": {"threshold": 5, "per_step_decay": 1},
    }
    (out_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(persona, sort_keys=False),
        encoding="utf-8",
    )
```

Then reference those personas:

```yaml
personas:
  - mobile-only-user
  - plain-language-reader
```

## Basic Fixture

```yaml
id: acme-inclusive-demo-path
name: Acme Inclusive Demo Path
mode: inclusive-ux
comparison_title: Acme Inclusive Demo Path
comparison_output: acme-inclusive-demo-path.html
url_template: https://www.example.com/
study_title: Acme Inclusive Demo Path ({variant})
task: >
  Starting from the homepage, find how you would contact the company or request
  a demo. Pay attention to whether labels, page layout, and form fields are
  clear enough for you to proceed confidently.
success_criteria: >
  The visitor finds a demo/contact path and can explain the next action without
  unresolved confusion about labels, forms, or page state.
personas:
  - mobile-only-user
  - low-confidence-user
  - plain-language-reader
runs_per_persona: 1
driver: edsl
max_steps: 8
max_concurrent_runs: 1
keep_runs: 8
analysis_driver: local
eval_policy: report_only
variants:
  - name: mobile
    device: iphone
  - name: desktop
    device: desktop
```

Save this as:

```text
examples/<site_or_product>/accessibility-inclusive-ux.yaml
```

## Device And Viewport Variants

Use built-in devices first:

```yaml
variants:
  - name: iphone
    device: iphone
  - name: pixel
    device: pixel
  - name: desktop
    device: desktop
```

For zoom or small-window behavior, use explicit viewport overrides in ad hoc
runs:

```bash
uxtest study run <study-id> --viewport 360x640 --mobile --touch --driver edsl
```

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/accessibility-inclusive-ux.yaml
```

Open:

```text
uxtest_store/comparisons/acme-inclusive-demo-path.html
```

Then inspect:

```text
uxtest_store/studies/<study-id>/analysis/log.html
```

## What To Inspect

Inspect:

- whether target controls are visible in mobile screenshots
- whether the agent scrolls past important content
- labels that require domain knowledge
- small or ambiguous form fields
- error messages and recovery paths
- repeated taps/clicks or failed actions
- whether completion state is visible and understandable

## How To Interpret Results

Treat this study as a way to locate inclusive UX risks. It can show where
constrained visitors hesitate, but it does not certify accessibility.

Read traces for:

1. **Visibility**
   Did the important control appear in the screenshot before the user needed
   it?

2. **Plain-language clarity**
   Did labels explain action and outcome without requiring domain knowledge?

3. **Interaction precision**
   Did the flow depend on small targets, dense menus, or ambiguous card clicks?

4. **Error recovery**
   Did forms and errors explain what happened and how to fix it?

5. **State recognition**
   Did the visitor understand success, failure, disabled controls, or loading
   states?

6. **Escalation**
   Which issues should be validated with automated accessibility tooling,
   keyboard-only manual testing, screen readers, or human participants?

## Common Findings

- Mobile layout hides a desktop-visible CTA.
- Cards or headings look clickable but are static.
- Form labels are too terse for low-confidence visitors.
- Error messages identify a problem but not the fix.
- Page relies on visual grouping that is lost on small screens.
- Jargon blocks visitors who are otherwise motivated.
- Confirmation state is too subtle.

## Narrative Report Shape

1. Summary: whether constrained visitors completed the task.
2. Context: task, constraints, and why inclusive access matters.
3. Method: personas, devices, viewport assumptions, and limitations.
4. Observed friction: visibility, labels, forms, errors, and recovery.
5. Accessibility risk indicators: issues to validate with formal tooling or
   human assistive-technology testing.
6. Conclusions: inclusive design implications.
7. Follow-on steps: copy, layout, form, focus, target-size, and audit work.

## Important Limitation

`uxtest` can use vision-capable EDSL models and Playwright screenshots, but it
does not replace automated accessibility tooling, screen readers, keyboard-only
manual tests, or participants with lived access needs. Use it to prioritize what
to inspect and where inclusive UX may break down.

## Example Narrative Summary

Use a style like this:

```text
This inclusive UX study tested whether constrained visitors could find the demo
path. Mobile-only users eventually found the menu, but the target action was
below several visually similar links and required extra scanning. The
plain-language reader understood "contact" but hesitated on product-specific
labels that did not explain outcome. These findings do not prove an
accessibility violation, but they identify risk areas: mobile nav hierarchy,
plain-language CTA wording, and form recovery. The next step is to validate the
same flow with automated accessibility checks and human participants using the
relevant access technologies.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to judge clarity or
first-click behavior from screenshots:

```bash
uv run uxtest humanize-export <study-id> \
  --template accessibility-inclusive-ux \
  --screenshots representative \
  --max-screenshots 8
```

Review and launch the generated survey:

```bash
uv run python uxtest_store/studies/<study-id>/analysis/humanize_survey.py
uv run python uxtest_store/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- What would you click first?
- Which label is clearest?
- What would make this form easier to complete?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Inclusive UX studies usually lead to:

- Formal accessibility audit: WCAG checks, keyboard testing, and screen-reader
  testing.
- Content comprehension: can plain-language readers understand the page?
- Conversion path testing: do layout and labels affect completion?
- Post-login workflow testing: do forms and errors work under constraints?
