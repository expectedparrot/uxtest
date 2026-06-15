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

## Using An Existing EDSL AgentList

If you have an EDSL `AgentList`, export the same selected agents for every
variant. The benchmark is only interpretable when the task, personas, device
mix, and step budget are held constant.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="enterprise-buyer",
            traits={
                "role": "enterprise buyer",
                "decision_goal": "compare vendors for a demo shortlist",
                "evidence_standard": "customer proof, credible positioning, clear next step",
            },
            instruction=(
                "Uses the same evidence standard for every site: category "
                "clarity, proof, demo/contact path, and risk signals."
            ),
        ),
        Agent(
            name="technical-evaluator",
            traits={
                "role": "technical evaluator",
                "decision_goal": "compare implementation feasibility",
                "evidence_standard": "docs, API, examples, integrations, security",
            },
            instruction=(
                "Compares sites by how quickly they provide concrete technical "
                "evidence and a route to deeper evaluation."
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

Then use the same names in the benchmark:

```yaml
personas:
  - enterprise-buyer
  - technical-evaluator
```

For competitor work, write persona instructions as comparison standards rather
than site-specific goals. Do not tell the persona what you expect a particular
site to do.

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

Save this as:

```text
examples/<benchmark_name>/competitive-benchmark.yaml
```

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<benchmark_name>/competitive-benchmark.yaml
```

Keep `max_concurrent_runs` conservative for public competitor sites. A
benchmark can multiply traffic quickly because each persona runs across every
variant.

Open:

```text
.uxtest/comparisons/competitive-demo-path.html
```

Then inspect the developer logs for individual variants:

```text
.uxtest/studies/<study-id>/analysis/log.html
```

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

## How To Interpret Results

Benchmark findings should compare observed paths, not just final outcomes.

Read across variants for:

1. **First useful action**
   Which site made the next step obvious fastest?

2. **Evidence before ask**
   Did the site earn confidence before asking for demo, signup, or contact
   information?

3. **Information scent**
   Which labels helped personas predict where useful evidence would be?

4. **Detours and recovery**
   Where did visitors open menus, scroll, use find, backtrack, or abandon a
   route?

5. **Persona-specific ranking**
   Did the same site win for buyers and technical evaluators, or did rankings
   diverge by role?

6. **Device effects**
   Did mobile navigation change which site performed best?

Avoid claiming precise quantitative superiority from a small synthetic sample.
Use counts to locate repeated patterns, then make qualitative claims grounded in
screenshots, actions, and trace reasoning.

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

## Example Narrative Summary

Use a style like this:

```text
This benchmark compared three sites on the same enterprise demo-evaluation task.
All sites exposed a demo or contact route, but they differed in how much
confidence they built before that ask. Competitor A gave the clearest category
and customer-proof path, while our site had stronger technical material that was
harder for buyers to discover. Competitor B had the fewest choices and produced
the fastest first action, but it left the technical evaluator with weaker
implementation evidence. The design implication is not simply to copy one
competitor; it is to combine clearer buyer routing with the technical proof that
already exists elsewhere on our site.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to compare
representative screenshots across variants:

```bash
uv run uxtest humanize-export <study-id> \
  --template competitive-benchmark \
  --screenshots representative \
  --max-screenshots 8
```

For full benchmark validation, export one study per variant and combine the
screenshots in a separate EDSL survey script. Keep the question wording and
answer options identical across variants.

Review before launch:

```bash
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- Which page makes the next step clearest?
- Which page looks most credible?
- Which page provides the best evidence for this task?
- What would you click first?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size, spacing, and answer presentation can be edited before launching.

## Follow-On Studies

Competitive benchmarking usually leads to:

- Task discovery: can visitors orient on the redesigned page?
- Conversion path testing: did borrowed patterns improve the target action?
- Content comprehension: can visitors repeat back the new positioning?
- Enterprise buying research: does stronger proof change buyer confidence?
- Longitudinal regression: did the redesign improve the benchmarked task over
  time?
