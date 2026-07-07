# Post-Login Workflow Testing

## What This Study Answers

A post-login workflow study asks whether authenticated users can complete a
specific product task from a known logged-in state. It tests navigation, labels,
permissions, data state, forms, confirmations, and recovery from mistakes inside
the application.

Use this study type for tasks like:

- create a project
- invite a teammate
- configure an integration
- export a report
- change billing details
- find an invoice
- approve an item
- update account settings

## When To Use It

Run this when the workflow requires authentication or role-specific state. It is
best for product surfaces where marketing-site study methods are too broad.

## Research Questions

1. Can the user find the workflow entry point?
2. Do labels match the user's mental model?
3. Do permissions or missing data block progress?
4. Are form fields and validation messages understandable?
5. Does the user recognize completion?
6. Are there role, data, or device-specific failures?

## Recommended Personas

Use personas tied to roles and permissions:

- `workspace-admin`: manages users, billing, security, and integrations
- `standard-user`: completes core workflow tasks with limited permissions
- `reviewer`: approves, comments, or exports but does not configure
- `support-operator`: searches records and resolves operational issues
- `new-team-member`: has low product familiarity and inherited workspace state

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList`, export personas whose role,
permission level, and data assumptions match the workflow being tested.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="workspace-admin",
            traits={
                "role": "workspace admin",
                "permissions": "admin",
                "workflow_goal": "invite and manage teammates",
                "product_familiarity": "medium",
            },
            instruction=(
                "Looks for workspace, members, users, teams, settings, or "
                "admin routes. Expects to have permission to invite teammates."
            ),
        ),
        Agent(
            name="standard-user",
            traits={
                "role": "standard user",
                "permissions": "limited",
                "workflow_goal": "complete core work without admin controls",
                "product_familiarity": "medium",
            },
            instruction=(
                "Looks for the workflow in primary product navigation and "
                "notices permission blockers or missing entry points."
            ),
        ),
    ]
)


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")


out_dir = Path("uxtest_store/personas")
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
  - workspace-admin
```

## Basic Fixture

```yaml
id: acme-invite-workflow
name: Acme Invite Workflow
mode: authenticated-workflow
comparison_title: Acme Invite Workflow
comparison_output: acme-invite-workflow.html
url_template: https://app.example.com/dashboard
study_title: Acme Invite Workflow ({variant})
task: >
  Starting from the logged-in dashboard, invite a teammate to this workspace.
  Continue until you find the invite path, complete the required fields if a
  test address is available, or explain what blocks completion.
success_criteria: >
  The visitor reaches the teammate invite flow and either completes a test
  invite or identifies the exact blocker.
personas:
  - workspace-admin
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
examples/<site_or_product>/post-login-workflow.yaml
```

## Auth And State

Use `setup_steps` or `auth_state` so the actual study begins after login.

```yaml
env_file: secrets.env
auth_state:
  load: uxtest_store/auth/admin-user.json
setup_steps:
  - type: find
    text: Dashboard
```

For workflows that mutate data, prepare disposable test accounts or fixtures.
Avoid using production accounts. If a workflow sends email, charges money,
changes permissions, or deletes data, use staging or a test bypass.

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/post-login-workflow.yaml
```

Open:

```text
uxtest_store/comparisons/acme-invite-workflow.html
```

Then inspect:

```text
uxtest_store/studies/<study-id>/analysis/log.html
```

For workflows that can send real invitations, update billing, delete data, or
change permissions, stop before the final commit unless the environment is
explicitly safe.

## What To Inspect

Inspect:

- start page after auth setup
- first navigation choice
- menus and settings areas opened
- permission or role blockers
- form field interpretation
- validation errors
- confirmation screen or absence of feedback
- whether the agent repeats actions or changes strategy

## How To Interpret Results

Post-login workflow studies are about product operations from a known state.
Do not mix login friction with the workflow unless login is part of the
research question.

Read traces for:

1. **Entry-point expectation**
   Where did the user expect the workflow to start?

2. **Permission clarity**
   Did the interface explain whether the user could or could not complete the
   task?

3. **State dependency**
   Did missing data, empty state, role setup, or prior configuration block the
   workflow?

4. **Form interpretation**
   Did labels, validation, and required fields make sense?

5. **Completion recognition**
   Did the product provide clear feedback that the workflow succeeded?

6. **Recovery**
   Did the user recover from mistakes, validation errors, or dead ends?

## Optional Checks

```yaml
checks:
  - id: reaches_invite_flow
    type: trace_contains
    text_any:
      - invite
      - teammate
      - member
      - user
    description: Trace should show entry into the invite workflow.
```

For destructive workflows, checks should stop before the destructive commit
unless the environment is explicitly safe.

## Common Findings

- Workflow lives under settings when users expect it in the main nav.
- Role permissions are unclear until late in the task.
- Empty data state removes the expected entry point.
- Confirmation feedback is weak or absent.
- Validation messages do not explain how to recover.
- Similar labels such as "Teams", "Users", "Members", and "Workspace" compete.
- Mobile layout hides secondary admin controls.

## Narrative Report Shape

1. Summary: whether users completed the workflow.
2. Context: role, starting state, and workflow importance.
3. Method: auth setup, personas, device, and data assumptions.
4. Workflow path: navigation, forms, blockers, and completion evidence.
5. Failure modes: permissions, labels, validation, state, or feedback.
6. Conclusions: product workflow changes.
7. Follow-on steps: state fixtures, role-specific tests, and regression checks.

## Example Narrative Summary

Use a style like this:

```text
This post-login workflow study tested whether a workspace admin could invite a
teammate from a known dashboard state. The admin eventually found the invite
flow, but only after opening both Settings and Workspace areas because the
labels "Users," "Members," and "Team" appeared to overlap. The form itself was
understandable, but completion feedback was weak: after submitting the test
address, the screen did not make it obvious whether an invitation was sent or
queued. The next step is to consolidate team-management labels and strengthen
confirmation feedback for admin actions.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to judge workflow
entry points or form clarity from screenshots:

```bash
uv run uxtest humanize-export <study-id> \
  --template post-login-workflow \
  --screenshots representative \
  --max-screenshots 8
```

Review and launch the generated survey:

```bash
uv run python uxtest_store/studies/<study-id>/analysis/humanize_survey.py
uv run python uxtest_store/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- Where would you click to start this workflow?
- What does this validation message mean?
- Has the task been completed on this screen?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Post-login workflow testing usually leads to:

- Onboarding activation: can new users reach the workflow in the first place?
- Information architecture: should settings, workspace, and team labels change?
- Accessibility inclusive UX: do forms, errors, and confirmations work under
  constraints?
- Longitudinal regression: did workflow fixes preserve completion over time?
