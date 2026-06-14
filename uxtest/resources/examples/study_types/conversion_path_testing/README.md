# Conversion Path Testing

## What This Study Answers

A conversion path study asks whether synthetic visitors can reach a target
action from a page or flow. Use it when the product question is not only "do
they understand this?" but "can they get to the business-critical next step?"

Use this study type to test paths to:

- schedule a demo
- start signup or account creation
- contact sales
- find pricing or request a quote
- start checkout
- download a report or gated asset
- complete a lead form

## When To Use It

Run this after task discovery when the intended action is known. It is also a
good regression study after nav, CTA, pricing, or form changes.

Do not use it as the first study if stakeholders disagree about what the visitor
is trying to do. In that case, run task discovery first and then convert the
observed intent into a narrower path test.

## Research Questions

1. What does the visitor click first on the way to the target action?
2. Can they identify the correct CTA or navigation path?
3. Which detours compete with the target action?
4. Where do they hesitate, loop, or abandon?
5. Do desktop and mobile visitors find the same path?
6. Do different personas interpret the same CTA differently?

## Recommended Personas

Use personas with distinct conversion motivations. For a B2B product, this
could include:

- `enterprise-buyer`: wants enough confidence to schedule a demo
- `technical-evaluator`: wants docs or implementation proof before a demo
- `budget-owner`: looks for pricing or procurement signals
- `ops-manager`: wants workflow fit and time-to-value

For ecommerce, use intent differences such as price-sensitive shopper,
repeat buyer, gift buyer, and low-confidence first-time buyer.

## Basic Fixture

```yaml
id: acme-demo-path
name: Acme Demo Path
mode: live-site-conversion
comparison_title: Acme Demo Path
comparison_output: acme-demo-path.html
url_template: https://www.example.com/
study_title: Acme Demo Path ({variant})
task: >
  Starting from the homepage, find the path you would use to schedule a demo.
  Continue until you reach the demo request, contact sales, or equivalent next
  step. Explain any hesitation before submitting personal information.
success_criteria: >
  The visitor reaches a demo/contact-sales path or a page that clearly explains
  how to request a demo.
personas:
  - enterprise-buyer
  - technical-evaluator
runs_per_persona: 1
driver: edsl
max_steps: 8
max_concurrent_runs: 2
keep_runs: 8
analysis_driver: local
eval_policy: report_only
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

## What To Inspect

Start with `log.html` and the animation index. Look for:

- first click and whether it targets the intended conversion path
- labels the agent used as evidence, such as "Demo", "Get started", or "Sales"
- detours into docs, products, pricing, login, or account dashboards
- form fields that create hesitation
- mobile navigation problems
- final URL and final visible page state

## Useful Eval Checks

When the intended path is known, add checks. Keep them broad enough to allow
reasonable route variation.

```yaml
checks:
  - id: reaches_demo_or_contact
    type: final_url
    expected_in: desktop
    url_contains_any:
      - demo
      - contact
      - sales
    description: Visitor should reach a demo or contact-sales path.

  - id: avoids_login_as_demo
    type: trace_absence
    action_contains: login
    description: Visitor should not mistake login for the demo path.
```

## How To Interpret Results

Completion is more meaningful here than in task discovery, but inspect the path,
not only the outcome. A visitor who reaches a demo page after six confused
steps is different from one who recognizes the right CTA immediately.

Common findings:

- Primary CTA leads to signup when buyers expect demo education.
- Pricing or docs compete with demo intent.
- Mobile menu hides the conversion path.
- The form appears before enough proof is available.
- "Get started" is ambiguous across login, signup, demo, and product tour.
- Visitors reach the right page but hesitate at required fields.

## Narrative Report Shape

Use this outline:

1. Summary: whether visitors reached the target action.
2. Context: why this conversion path matters.
3. Method: personas, devices, URL, runs, and step budget.
4. Path behavior: first clicks, detours, loops, and final pages.
5. Conversion friction: labels, forms, missing proof, or mobile nav.
6. Conclusions: what blocks or helps conversion.
7. Follow-on steps: CTA copy, nav changes, form changes, and regression checks.
