# Competitive Benchmark Studies

## What This Study Answers

A competitive benchmark study runs the same task across multiple sites,
products, or variants. It asks how options compare on first-click behavior,
completion, confusion, credibility, information scent, and evidence quality.

Use this study type when stakeholders ask "how do we compare?" or when a design
team wants concrete examples of what competitors make easier or harder.

## When To Use It

Run this for:

- homepage first impressions across vendors
- demo path comparison
- pricing findability
- docs/API discoverability
- enterprise credibility comparison
- onboarding flow comparison across variants
- before/after site redesign comparison

Keep tasks narrow and consistent. "Evaluate these companies" is often too
broad; "find enough evidence to decide whether to schedule a demo" is better.

## Research Questions

1. Which site makes the task easiest to start?
2. Which labels or layouts create the clearest information scent?
3. Where do visitors detour or hesitate?
4. Which site provides stronger proof or credibility?
5. Do mobile differences change the ranking?
6. What patterns should be borrowed, avoided, or tested?

## Recommended Personas

Use the same personas across every competitor or variant. Typical benchmark
personas include:

- `enterprise-buyer`: evaluates credibility and demo paths
- `technical-evaluator`: evaluates docs, integration, and implementation proof
- `budget-owner`: evaluates pricing and procurement clarity
- `operator`: evaluates workflow fit and operational details

## Basic Fixture Pattern

Use variants for each site or design. Keep task, personas, device, and step
budget constant.

```yaml
id: acme-competitive-demo-path
name: Acme Competitive Demo Path
mode: competitive-benchmark
comparison_title: Competitive Demo Path Benchmark
comparison_output: competitive-demo-path.html
study_title: Demo Path Benchmark ({variant})
task: >
  Starting from this company's homepage, decide whether you would schedule a
  demo. Find the clearest path to request a demo or contact sales, and note what
  evidence makes you more or less confident.
success_criteria: >
  The visitor finds a demo/contact-sales path or enough evidence to explain why
  they would not continue.
personas:
  - enterprise-buyer
  - technical-evaluator
runs_per_persona: 1
driver: edsl
max_steps: 8
max_concurrent_runs: 1
keep_runs: 6
analysis_driver: local
eval_policy: report_only
variants:
  - name: our-site
    url: https://www.example.com/
    device: desktop
  - name: competitor-a
    url: https://www.competitor-a.example/
    device: desktop
  - name: competitor-b
    url: https://www.competitor-b.example/
    device: desktop
```

For desktop/mobile benchmarking, duplicate variants with device-specific names:
`our-site-mobile`, `competitor-a-mobile`, and so on.

## What To Inspect

Inspect the comparison report first, then each `log.html`.

Look for:

- first action by site
- number of steps to useful evidence
- demo/contact/pricing path clarity
- content or proof found before conversion ask
- repeated actions, backtracking, or `find` use
- mobile nav differences
- final confidence and reason for stopping

## Optional Checks

Use comparable checks across every variant:

```yaml
checks:
  - id: reaches_demo_or_sales
    type: final_url
    url_contains_any:
      - demo
      - sales
      - contact
    description: Visitor should find a demo/contact route.
```

Do not over-interpret small differences in synthetic counts. Use counts to
locate patterns, then explain the observed paths.

## Common Findings

- Competitors use clearer category labels.
- Our site has stronger proof but weaker routing.
- One site earns trust before asking for contact details.
- Mobile menus create different rankings than desktop.
- Competitor docs or examples make technical evaluation easier.
- Pricing labels vary enough to change first-click behavior.
- A site with fewer choices can outperform a richer but ambiguous IA.

## Narrative Report Shape

1. Summary: which site or variant performed best for the task.
2. Context: why the benchmark was run and what was compared.
3. Method: same task, personas, devices, and run counts across variants.
4. Comparative paths: first clicks, evidence found, detours, and outcomes.
5. Strengths and weaknesses by site.
6. Patterns to adopt or avoid.
7. Follow-on steps: focused redesign hypotheses and regression checks.
