# Task Discovery Study

## What This Study Answers

A task discovery study asks whether first-time visitors can orient themselves on
a page before they are given a narrow conversion or workflow task.

Use this study type when you want to know:

- Can users figure out what this product, page, or site is for?
- What do they click first?
- What do they misunderstand?
- Where do they hesitate before taking action?

This is usually the first study to run on a homepage, landing page, product
page, documentation entry point, marketplace listing, or internal tool
dashboard.

## When To Use It

Run a task discovery study when:

- a page is new or recently redesigned
- stakeholders disagree about whether the page is clear
- conversion is weak and you do not know whether the problem is messaging,
  navigation, trust, or offer clarity
- visitors are taking the wrong first action
- a product has multiple audiences and the page may not make the right path
  obvious

Do not use this as the only study if you already know the user has a precise
goal like "reset password" or "download invoice." In that case, run a
workflow-specific study after discovery.

## Research Questions

Use these as the default research questions:

1. What does the visitor think this page is for?
2. What is the first action they want to take?
3. Which labels, claims, or visual elements guide that first action?
4. What information is missing before they feel confident?
5. What do they misunderstand about the product, audience, or next step?
6. Do desktop and mobile visitors orient differently?

## Recommended Personas

Pick three to five personas who plausibly represent different interpretations of
the page. The right personas depend on the product, audience, and research
question. Use personas that represent distinct reasons someone might land on the
page, not just demographic variation.

For example, if you were studying a B2B research product page, a plausible
starting set might be:

- `startup-founder`: evaluates value quickly and looks for proof or pricing
- `enterprise-insights-lead`: looks for enterprise credibility and demo paths
- `survey-ops-manager`: looks for operational workflow fit
- `developer-builder`: looks for docs, API, examples, and technical proof
- `academic-researcher`: looks for methods, validity, and research credibility

Avoid personas that are too generic. The best personas have a job, a decision
pressure, and a bias about what evidence matters.

For a different study, choose a different set. A healthcare portal might use
patients, caregivers, billing staff, and clinicians. A developer documentation
site might use a first-time integrator, senior platform engineer, technical
decision maker, and support engineer.

## Using An Existing EDSL AgentList

If you already have personas as an EDSL `AgentList`, use that as the source of
truth and export the agents into `.uxtest/personas/*.yaml`.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="enterprise-insights-lead",
            traits={
                "role": "enterprise insights lead",
                "technical_depth": "low",
                "buying_goal": "decide whether to book a demo",
                "time_pressure": "medium",
            },
            instruction=(
                "Looks for enterprise credibility, demos, case studies, "
                "security, customer proof, and clear contact paths."
            ),
        ),
        Agent(
            name="developer-builder",
            traits={
                "role": "developer",
                "technical_depth": "high",
                "workflow_focus": "API, docs, examples, automation",
                "buying_goal": "decide whether the product is programmable",
            },
            instruction=(
                "Looks for documentation, API references, GitHub/examples, "
                "quickstarts, and concrete code-oriented proof."
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

Then reference those exported persona names in the fixture:

```yaml
personas:
  - enterprise-insights-lead
  - developer-builder
```

Notes:

- Keep the EDSL `traits` field structured. `uxtest` snapshots these traits into
  each run and passes them to the EDSL browser-decision agent.
- Put task-specific decision bias in `instruction`; it becomes `goals_bias` in
  the persona YAML.
- Use stable names. Fixture studies refer to persona filenames, so changing a
  persona name changes the study input.
- If the `AgentList` is large, sample deliberately. For task discovery, three
  to five high-contrast personas usually produce more interpretable results
  than dozens of similar personas.

## Basic Fixture

Create a fixture like this:

```yaml
id: acme-task-discovery
name: Acme Task Discovery
mode: live-site-task-discovery
comparison_title: Acme Task Discovery
comparison_output: acme-task-discovery.html
url_template: https://www.example.com/
study_title: Acme Task Discovery ({variant})
task: >
  You are visiting this page for the first time. Figure out what this product
  or page is for, what you would click next, and what is confusing or missing
  before you would take action. Stop when you can explain the page's purpose,
  your next click, and any remaining hesitation.
success_criteria: >
  The visitor can explain what the page is for, choose a plausible next action,
  and name anything confusing or missing.
personas:
  - startup-founder
  - enterprise-insights-lead
  - survey-ops-manager
runs_per_persona: 1
driver: edsl
max_steps: 6
max_concurrent_runs: 2
keep_runs: 8
analysis_driver: local
eval_policy: report_only
animation_delay: 250
animation_max_width: 640
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

Save it as:

```text
examples/<site_or_product>/task-discovery.yaml
```

For a public live site, keep `max_concurrent_runs` at `1` or `2` to avoid
launching too many browser sessions from one IP at once.

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/task-discovery.yaml
```

The command will:

1. create or update fixture-backed studies
2. run Playwright browser sessions
3. ask EDSL for each browser decision
4. capture screenshots and traces
5. analyze the study
6. generate GIF animations
7. generate a comparison report

## What To Inspect First

Open the comparison report:

```text
.uxtest/comparisons/acme-task-discovery.html
```

Then inspect each study's developer log:

```text
.uxtest/studies/<study-id>/analysis/log.html
```

Use the log to answer:

- What did the agent see above the fold?
- What did it click first?
- Did it scroll, open navigation, use `find`, or leave the site?
- Did the selected action visibly advance the page?
- Did it finish because it understood the page, or because it gave up?

## How To Interpret Results

For task discovery, raw completion rate is useful but not enough. A run can be
marked `max_steps` and still contain valuable evidence about first-click intent
or confusion.

Read the traces for four moments:

1. **Initial interpretation**
   What did the persona think the page was about after the first screenshot?

2. **First action**
   Did they click the primary CTA, open navigation, scroll, search/find, or do
   nothing?

3. **Misunderstanding**
   Did they expect a heading to be clickable, mistake login for demo/signup, or
   choose a path intended for another audience?

4. **Stopping point**
   Did they reach enough confidence, hit a dead end, loop, or leave for an
   external page?

## Common Findings

Typical findings from this study type:

- The page does not make the product category clear.
- The primary CTA implies the wrong next step.
- Visitors expect top-level headings or product cards to navigate.
- Mobile visitors miss desktop-visible navigation.
- Visitors understand the broad category but not the specific workflow.
- Trust or proof is missing before a higher-commitment action.
- Persona groups choose different first paths, implying the page needs clearer
  audience routing.

## Narrative Report Outline

After the technical report is generated, write a narrative report with this
shape:

1. **Summary**
   Say whether visitors understood the page and what the main first-click
   pattern was.

2. **Context**
   Explain the page, audience, and why task discovery matters.

3. **Method**
   List target URL, personas, devices, run counts, and EDSL/Playwright method.

4. **What Visitors Did**
   Describe first-clicks and paths by persona/device.

5. **What They Understood**
   Summarize the product/page interpretation.

6. **Where They Hesitated**
   Explain confusion, missing evidence, loops, or dead ends.

7. **Main Conclusions**
   Turn the observed behavior into design implications.

8. **Follow-On Steps**
   Recommend page changes and additional studies.

## Example Narrative Summary

Use a style like this:

```text
This task discovery study tested whether first-time visitors could understand
the homepage and choose a sensible next action. The synthetic visitors generally
recognized that the page described a research automation product, but their
first actions diverged: enterprise-oriented personas looked for demo/contact
paths, operational personas opened product areas, and technical personas looked
for docs/examples. The main confusion was that "Get started" behaved like an
authentication path while several visitors expected it to explain or initiate
evaluation. The next design step is to separate self-serve account creation from
buyer education and make audience-specific paths visible from the first screen.
```

## Optional Checks

If you know the desired first action, add an eval check. Example:

```yaml
checks:
  - id: first_click_opens_product_overview
    type: first_click
    expected_in: desktop
    action_contains: product
    final_url_contains: /products
    description: First product-learning click should route to product overview.
```

Use strict checks carefully. In discovery work, surprising first clicks are
often the point of the study.

## Follow-On Studies

A task discovery study usually leads to one of these:

- Conversion path testing: can visitors reach demo/signup/contact?
- Information architecture: can visitors find specific content?
- Content comprehension: can visitors summarize the value proposition?
- Enterprise buying research: can buyers find security, procurement, support,
  and proof?
- Longitudinal regression: did a redesign fix the discovery issue?
