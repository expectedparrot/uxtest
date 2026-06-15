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

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList` for your audience, use it to create
reader personas. For comprehension work, the important traits are domain
knowledge, decision context, vocabulary familiarity, and skepticism toward
claims.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="domain-expert",
            traits={
                "role": "experienced category buyer",
                "domain_familiarity": "high",
                "reading_goal": "separate concrete claims from vague claims",
                "skepticism": "high",
            },
            instruction=(
                "Reads quickly, recognizes category jargon, and notices when "
                "claims lack examples, mechanism, or proof."
            ),
        ),
        Agent(
            name="newcomer",
            traits={
                "role": "first-time visitor",
                "domain_familiarity": "low",
                "reading_goal": "understand what the page is for",
                "skepticism": "medium",
            },
            instruction=(
                "Gets confused by unexplained terms and needs concrete examples "
                "before deciding what the product does."
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
        "frustration": {"threshold": 5, "per_step_decay": 1},
    }
    (out_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(persona, sort_keys=False),
        encoding="utf-8",
    )
```

Then reference those personas in the study fixture:

```yaml
personas:
  - domain-expert
  - newcomer
```

For content comprehension, avoid personas that are only demographic labels.
What matters is what vocabulary they know, what they are trying to decide, and
what kind of evidence they consider explanatory.

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

Save this as:

```text
examples/<site_or_product>/content-comprehension.yaml
```

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/content-comprehension.yaml
```

This will run the reading/scanning task, capture screenshots and visible text,
ask EDSL for each browsing decision, and generate the comparison report.

Open:

```text
.uxtest/comparisons/acme-content-comprehension.html
```

Then inspect the detailed logs:

```text
.uxtest/studies/<study-id>/analysis/log.html
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

## How To Interpret Results

Content comprehension is about mental model formation. Do not reduce it to
whether the agent reached a URL.

Read traces for:

1. **First summary**
   What did the visitor think the page was about before scrolling?

2. **Audience inference**
   Who did they think the page was written for?

3. **Value reconstruction**
   Can they explain the practical benefit in their own words?

4. **Claim quality**
   Which statements were treated as concrete, vague, unsupported, or
   unbelievable?

5. **Vocabulary failure**
   Which product names, acronyms, abstractions, or category terms needed more
   explanation?

6. **Reading-order effect**
   Did later sections repair confusion from the first screen, and did mobile
   change when that repair happened?

Strong findings usually quote the visitor's interpretation, then compare it to
the intended message. The gap between those two is the product/design issue.

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

## Example Narrative Summary

Use a style like this:

```text
This content comprehension study tested whether first-time readers could explain
the page's offer, audience, and next step after scanning it. The domain expert
understood the broad category but wanted more concrete examples before trusting
the claims. The newcomer repeated several high-level phrases from the page but
could not explain the workflow in practical terms. The main issue is that the
page communicates ambition before mechanism: visitors hear that the product is
powerful, but they do not yet know what they would do with it on day one. The
next step is to add a plain-language workflow example near the top and test
whether visitors can repeat it back accurately.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real readers to interpret the same
screenshots:

```bash
uv run uxtest humanize-export <study-id> \
  --template content-comprehension \
  --screenshots representative \
  --max-screenshots 8
```

Review the generated script first:

```bash
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- What do you think this page is for?
- Who do you think this is for?
- Which phrase is least clear?
- What would you click or read next?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
dimensions and button-style question presentation can be adjusted before launch.

## Follow-On Studies

Content comprehension usually leads to:

- Task discovery: do clearer messages change first-click behavior?
- Conversion path testing: can readers act after they understand the page?
- Enterprise buying research: do stakeholders find enough proof after the
  message is clear?
- Competitive benchmarking: do competitors explain the same concept more
  concretely?
- Longitudinal regression: did a rewrite improve comprehension without hurting
  findability?
