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

## What To Inspect

Inspect:

- whether target controls are visible in mobile screenshots
- whether the agent scrolls past important content
- labels that require domain knowledge
- small or ambiguous form fields
- error messages and recovery paths
- repeated taps/clicks or failed actions
- whether completion state is visible and understandable

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
