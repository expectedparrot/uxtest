# Onboarding Activation

## What This Study Answers

An onboarding activation study asks whether a newly signed-up or invited user
can reach the first meaningful product action. It tests first-run setup, empty
states, templates, prompts, permission requests, and whether users understand
what to do after landing inside the product.

Use this study type when the key question is "can a new user get started in the
product?" rather than "can a visitor decide to sign up?"

## When To Use It

Run this after account creation, invitation flows, product redesigns, template
changes, onboarding checklist changes, or new user-role launches. It requires a
test account or reliable setup state.

## Research Questions

1. Does the user understand what the product expects them to do first?
2. Can they choose the right setup path or template?
3. Are empty states instructive or confusing?
4. Do permission, data, or integration prompts block progress?
5. Can the user reach a first meaningful action within the step budget?
6. Do different roles need different onboarding routes?

## Recommended Personas

Use personas based on product role and first-run intent:

- `new-admin`: sets up workspace, users, permissions, or integrations
- `new-individual-user`: wants to complete a first task quickly
- `template-seeker`: wants a starting point rather than blank setup
- `technical-setup-user`: expects API keys, imports, or integrations
- `low-confidence-new-user`: needs plain instructions and avoids risky choices

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList`, export first-run personas based on
role, setup goal, confidence, and tolerance for blank-state ambiguity.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="new-admin",
            traits={
                "role": "new workspace admin",
                "first_run_goal": "set up the workspace for a team",
                "setup_bias": "users, permissions, integrations",
                "confidence": "medium",
            },
            instruction=(
                "Looks for workspace setup, team invites, permissions, "
                "integrations, and clear confirmation that setup worked."
            ),
        ),
        Agent(
            name="template-seeker",
            traits={
                "role": "new individual user",
                "first_run_goal": "start from a useful template",
                "setup_bias": "templates, examples, guided workflow",
                "confidence": "low",
            },
            instruction=(
                "Avoids blank-canvas choices and looks for templates, examples, "
                "checklists, or guided first actions."
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

Then reference those personas:

```yaml
personas:
  - new-admin
  - template-seeker
```

## Basic Fixture

```yaml
id: acme-onboarding
name: Acme Onboarding Activation
mode: authenticated-onboarding
comparison_title: Acme Onboarding Activation
comparison_output: acme-onboarding.html
url_template: https://app.example.com/
study_title: Acme Onboarding ({variant})
task: >
  You are a newly invited user opening this product for the first time. Figure
  out what to do first and try to complete the first meaningful setup or product
  action. Stop when you have successfully started a real workflow or when you
  are blocked.
success_criteria: >
  The visitor reaches a meaningful first action such as creating a project,
  choosing a template, inviting a teammate, importing data, or starting a
  workflow.
personas:
  - new-admin
  - new-individual-user
runs_per_persona: 1
driver: edsl
max_steps: 10
max_concurrent_runs: 1
keep_runs: 6
analysis_driver: local
eval_policy: report_only
variants:
  - name: desktop
    device: desktop
```

Save this as:

```text
examples/<site_or_product>/onboarding-activation.yaml
```

## Auth And Setup

Use deterministic setup to reach a clean first-run state. Avoid asking EDSL to
handle credentials.

```yaml
env_file: secrets.env
redact_patterns:
  - "test-user-[^\\s]+"
auth_state:
  save: .uxtest/auth/onboarding-user.json
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

For repeated runs, load a prepared session:

```yaml
auth_state:
  load: .uxtest/auth/onboarding-user.json
```

Use fresh or reset test accounts when possible. Reusing a fully activated
account can hide onboarding problems.

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/onboarding-activation.yaml
```

Open:

```text
.uxtest/comparisons/acme-onboarding.html
```

Then inspect:

```text
.uxtest/studies/<study-id>/analysis/log.html
```

Authenticated onboarding studies should run against staging, disposable
accounts, or safe seeded accounts. Do not let a study mutate production data
unless the fixture is explicitly designed for that.

## What To Inspect

Inspect:

- first in-product screen after setup
- whether the agent understands empty states
- first action chosen from a checklist, template gallery, or blank canvas
- prompts that feel mandatory but are not
- integration or permission blockers
- whether success requires prior domain knowledge
- loops between dashboard, settings, and help

## How To Interpret Results

Onboarding activation is about whether the user reaches a first meaningful
action, not merely whether they click through welcome screens.

Read traces for:

1. **Initial product model**
   Did the user understand what the product expected from them first?

2. **Path selection**
   Did they choose checklist, template, blank project, import, invite, or
   settings, and did that match their role?

3. **Blank-state clarity**
   Did empty states explain action, value, and completion?

4. **Prompt timing**
   Did integrations, permissions, or data-import prompts appear before the user
   had enough context?

5. **Activation evidence**
   Did the product show that the first action worked?

6. **Role mismatch**
   Did admin and end-user setup routes compete or confuse each other?

## Common Findings

- Empty state describes value but not the next action.
- Multiple setup options appear equally important.
- Templates help only if labels match user intent.
- Permission prompts appear before trust is established.
- Admin and end-user onboarding routes conflict.
- Users reach an action but cannot tell whether it worked.
- Returning sessions mask first-run friction.

## Narrative Report Shape

1. Summary: whether new users activated.
2. Context: product role, setup state, and first meaningful action.
3. Method: account setup, personas, device, and run count.
4. First-run behavior: initial screen, chosen path, and detours.
5. Activation friction: empty states, prompts, permissions, or ambiguity.
6. Conclusions: onboarding changes that would increase activation.
7. Follow-on steps: test-account fixtures, checklist changes, template labels,
   and longitudinal regression.

## Example Narrative Summary

Use a style like this:

```text
This onboarding activation study tested whether newly invited users could reach
a meaningful first product action from a clean account. The new admin found team
setup options quickly but hesitated because workspace setup, integration setup,
and project creation appeared equally urgent. The template-seeker understood
the product value but avoided the blank project path and looked for examples
that were not visible above the fold. The main onboarding issue is priority:
the product offers several plausible starts but does not make the right first
action role-specific. The next step is to split admin setup from individual
activation and add stronger completion feedback after the first action.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to judge first-run
clarity from screenshots:

```bash
uv run uxtest humanize-export <study-id> \
  --template onboarding-activation \
  --screenshots representative \
  --max-screenshots 8
```

Review and launch the generated survey:

```bash
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- What would you do first on this screen?
- Which setup option best matches your goal?
- How would you know that setup worked?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Onboarding activation usually leads to:

- Post-login workflow testing: can activated users complete role-specific work?
- Information architecture: can users find setup, templates, settings, or help?
- Content comprehension: do empty states explain value and action?
- Longitudinal regression: did onboarding changes improve activation over time?
