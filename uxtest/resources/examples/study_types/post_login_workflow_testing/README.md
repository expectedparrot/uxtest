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

## Auth And State

Use `setup_steps` or `auth_state` so the actual study begins after login.

```yaml
env_file: secrets.env
auth_state:
  load: .uxtest/auth/admin-user.json
setup_steps:
  - type: find
    text: Dashboard
```

For workflows that mutate data, prepare disposable test accounts or fixtures.
Avoid using production accounts. If a workflow sends email, charges money,
changes permissions, or deletes data, use staging or a test bypass.

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
