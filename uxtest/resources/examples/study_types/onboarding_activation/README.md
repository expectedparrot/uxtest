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

## Auth And Setup

Use deterministic setup to reach a clean first-run state. Avoid asking EDSL to
handle credentials.

```yaml
env_file: secrets.env
redact_patterns:
  - "test-user-[^\\s]+"
auth_state:
  save: uxtest_store/auth/onboarding-user.json
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
  load: uxtest_store/auth/onboarding-user.json
```

Use fresh or reset test accounts when possible. Reusing a fully activated
account can hide onboarding problems.

## What To Inspect

Inspect:

- first in-product screen after setup
- whether the agent understands empty states
- first action chosen from a checklist, template gallery, or blank canvas
- prompts that feel mandatory but are not
- integration or permission blockers
- whether success requires prior domain knowledge
- loops between dashboard, settings, and help

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
