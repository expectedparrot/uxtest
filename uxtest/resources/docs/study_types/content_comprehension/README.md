# Content Comprehension

## What This Study Answers

A content comprehension study asks whether visitors understand the message after
scanning a page or content area. It tests interpretation: product category,
value proposition, audience, claims, jargon, proof, and next steps.

Use this when the question is "what do visitors think this says?" rather than
"can they click to the right page?"

## When To Use It

Run this for homepages, landing pages, pricing pages, product pages, docs
intros, help articles, onboarding copy, and policy pages. It is useful before
and after copy changes because the same page can be visually polished but
conceptually unclear.

## Research Questions

1. What does the visitor think the page is about?
2. Who do they think the page is for?
3. What value proposition do they repeat back?
4. Which claims are clear, vague, or unbelievable?
5. Which terms or acronyms cause confusion?
6. What would they do next after reading?

## Recommended Personas

Choose personas with different domain familiarity:

- `domain-expert`: can detect vague claims and missing details
- `newcomer`: reveals jargon and category confusion
- `buyer`: looks for value, proof, and next steps
- `technical-reader`: checks whether technical claims are concrete
- `low-confidence-reader`: reads carefully and hesitates on ambiguity

## Basic Fixture

```yaml
id: acme-content-comprehension
name: Acme Content Comprehension
mode: live-site-content-comprehension
comparison_title: Acme Content Comprehension
comparison_output: acme-content-comprehension.html
url_template: https://www.example.com/
study_title: Acme Content Comprehension ({variant})
task: >
  Read and scan this page as a first-time visitor. Explain what you think the
  product or page is for, who it is for, what claims seem important, what is
  confusing, and what you would do next. Scroll as needed, but focus on
  understanding rather than completing a transaction.
success_criteria: >
  The visitor can accurately summarize the page's purpose, audience, main value
  proposition, confusing claims, and plausible next step.
personas:
  - newcomer
  - buyer
  - technical-reader
runs_per_persona: 1
driver: edsl
max_steps: 6
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

Look for:

- first interpretation after above-the-fold content
- phrases the agent repeats or misreads
- claims treated as evidence vs fluff
- confusion around product category, audience, or workflow
- whether scrolling improves comprehension
- whether mobile changes the reading order
- next step the visitor chooses after understanding the content

## Optional Checks

If there are must-understand concepts, use trace-content checks:

```yaml
checks:
  - id: understands_core_category
    type: trace_contains
    text_any:
      - research automation
      - survey
      - interview
    description: Visitor should identify the core product category.
```

Do not overfit wording. The model may paraphrase valid understanding.

## Common Findings

- Visitors understand the category but not the specific workflow.
- Hero copy is memorable but not explanatory.
- Claims lack proof or examples.
- Jargon hides the practical use case.
- Audience is ambiguous across buyer, builder, and end user.
- Scrolling reveals clarity that is absent above the fold.
- CTA appears before visitors know why they would click it.

## Narrative Report Shape

1. Summary: what visitors understood and misunderstood.
2. Context: page, audience, and communication goal.
3. Method: personas, devices, and reading/scanning task.
4. Interpretation: product category, audience, value, and next step.
5. Confusion: jargon, vague claims, missing examples, or proof gaps.
6. Device differences: above-the-fold and mobile reading order.
7. Conclusions: copy and content hierarchy implications.
8. Follow-on steps: rewrite tests, task discovery, or conversion path testing.
