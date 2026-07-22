# Feature Findability

## What This Study Answers

A feature findability study asks whether visitors can determine if a product
supports a specific feature, integration, workflow, use case, or capability.
The outcome is not merely "found a page"; it is whether the visitor finds enough
evidence to believe the capability exists and understand what to do next.

Use this study type for questions like:

- Does this product support SSO?
- Can it integrate with Salesforce?
- Does it have an API?
- Can teams export data?
- Is there support for mobile approvals?
- Can an admin invite teammates?

## When To Use It

Run this when sales, support, product, or docs teams repeatedly answer the same
capability question. It is also useful before launches: a feature can exist but
still be effectively invisible to evaluators.

## Research Questions

1. Where does the visitor look for the capability?
2. Which words do they expect the site to use?
3. Do they find proof, or only vague marketing claims?
4. Can they distinguish feature support from adjacent capabilities?
5. What evidence would make them confident?
6. What next action would they take after finding or failing to find it?

## Recommended Personas

Base personas on why the feature matters:

- `technical-evaluator`: needs docs, API details, limits, and implementation
  evidence
- `admin-buyer`: needs configuration, permissions, security, and rollout details
- `end-user`: needs workflow fit and plain-language confirmation
- `procurement-reviewer`: needs plan availability, support, and contract terms

## Using An Existing EDSL AgentList

If you have an EDSL `AgentList`, export personas with different evidence
standards for the same capability. A buyer, admin, and developer can all ask
"does this support SSO?" but they need different proof.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="technical-evaluator",
            traits={
                "role": "technical evaluator",
                "capability_target": "API or integration support",
                "evidence_needed": "docs, examples, API references, limits",
                "confidence_threshold": "high",
            },
            instruction=(
                "Looks for concrete implementation evidence, not just broad "
                "marketing claims about integrations or automation."
            ),
        ),
        Agent(
            name="admin-buyer",
            traits={
                "role": "admin buyer",
                "capability_target": "team administration and permissions",
                "evidence_needed": "configuration, roles, rollout, support",
                "confidence_threshold": "medium",
            },
            instruction=(
                "Looks for plain-language feature confirmation, admin workflow "
                "details, plan availability, and support expectations."
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
  - technical-evaluator
  - admin-buyer
```

Set `capability_target` and `evidence_needed` narrowly. Feature findability is
most useful when the expected proof can be named before the run.

## Basic Fixture

```yaml
id: acme-api-findability
name: Acme API Findability
mode: live-site-feature-findability
comparison_title: Acme API Findability
comparison_output: acme-api-findability.html
url_template: https://www.example.com/
study_title: Acme API Findability ({variant})
task: >
  Starting from the homepage, determine whether this product has an API or
  developer integration path. Find the strongest evidence you can. Stop when
  you are confident it exists, confident it does not, or blocked.
success_criteria: >
  The visitor finds API, developer, integration, docs, or example evidence
  sufficient to judge whether the capability exists.
personas:
  - technical-evaluator
  - admin-buyer
runs_per_persona: 1
driver: edsl
max_steps: 8
max_concurrent_runs: 2
keep_runs: 8
analysis_driver: local
eval_policy: report_only
overrides:
  model: gpt-4o
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

Save this as:

```text
examples/<site_or_product>/feature-findability.yaml
```

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/feature-findability.yaml
```

Open the comparison report:

```text
uxtest_store/comparisons/acme-api-findability.html
```

Then inspect detailed logs:

```text
uxtest_store/studies/<study-id>/analysis/log.html
```

## What To Inspect

Inspect:

- search terms or `find` text the agent uses
- whether it opens docs, resources, product menus, or footer links
- whether feature mentions are concrete or vague
- whether the agent confuses adjacent features
- screenshots of evidence pages
- final reasoning about confidence

## How To Interpret Results

Feature findability has three possible outcomes:

1. **Confirmed support**
   The visitor finds concrete evidence that the capability exists.

2. **Ambiguous support**
   The visitor finds suggestive language but cannot tell whether the capability
   is real, available, or relevant to their use case.

3. **Not findable**
   The visitor cannot find evidence, even if the product may support the
   capability elsewhere.

Read traces for the vocabulary the persona tries, the pages they expect to hold
proof, and the evidence threshold they apply. The most useful finding is often
that the product supports the feature but only one audience can prove it.

Classify evidence quality:

- **Concrete**: docs, API references, screenshots, examples, configuration
  details, limits, plan tables.
- **Suggestive**: marketing claims, broad feature labels, logos, vague
  "integrations" language.
- **Missing**: no reference, dead-end search, or proof hidden behind sales.

## Optional Checks

```yaml
checks:
  - id: finds_api_evidence
    type: trace_contains
    text_any:
      - API
      - developer
      - docs
      - integration
    description: Trace should contain capability evidence terms.
```

Prefer evidence-based checks over final URL checks because feature proof may
appear in many places.

## Common Findings

- Feature exists but is hidden under unexpected labels.
- Marketing claims are too broad to prove support.
- Docs prove the feature, but buyer pages do not link to docs.
- Visitors confuse integrations, API, exports, and automation.
- Plan availability or limits are missing.
- Mobile visitors miss feature cards or comparison tables.
- Visitors find evidence but cannot decide whether to contact sales or self
  serve.

## Narrative Report Shape

1. Summary: whether visitors could determine feature support.
2. Context: why the feature matters to each persona.
3. Method: feature target, personas, devices, and step budget.
4. Search path: labels, menus, docs, and detours used.
5. Evidence quality: concrete proof vs ambiguous claims.
6. Conclusions: what makes the feature findable or hidden.
7. Follow-on steps: copy, docs links, feature pages, comparison tables, and eval
   checks.

## Example Narrative Summary

Use a style like this:

```text
This feature findability study tested whether visitors could determine if the
product offers an API. The technical evaluator found developer-oriented
evidence after opening documentation, but the admin buyer saw only broad
"integration" language and could not tell whether API access was available,
included, or sales-gated. The capability appears to exist, but the site does not
make it equally provable for all evaluators. The next step is to connect buyer
pages to API proof and add a plain-language feature statement that links to
technical details.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to judge whether a
screenshot proves feature support:

```bash
uv run uxtest humanize-export <study-id> \
  --template feature-findability \
  --screenshots representative \
  --max-screenshots 8 \
  --output ./humanize/jobs.ep
```

Review and launch the generated survey:

```bash
ep inspect ./humanize/jobs.ep
ep humanize create --jobs ./humanize/jobs.ep --scenario_method ordered --schema ./humanize/humanize_schema.json
```

Useful human questions include:

- Does this screen prove the feature exists?
- What words would you search for to find this capability?
- What evidence is missing before you would trust the claim?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Feature findability usually leads to:

- Information architecture: should the capability live under a different label
  or menu?
- Content comprehension: do visitors understand what the feature claim means?
- Enterprise buying research: does the feature proof satisfy buying
  stakeholders?
- Conversion path testing: can interested visitors reach docs, contact, or
  signup after finding the feature?
