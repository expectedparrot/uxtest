# Enterprise Buying Research

## What This Study Answers

An enterprise buying study asks whether stakeholders can find enough evidence to
take the next buying step. It tests credibility, seriousness, implementation
fit, procurement readiness, security, support, and contact paths.

Use this study type when the target visitor is not merely browsing. They are
deciding whether the company looks credible enough to evaluate, shortlist, or
schedule a demo.

## When To Use It

Run this for B2B homepages, product pages, security pages, pricing pages,
enterprise landing pages, and documentation entry points. It is especially
useful when the product is new, technical, high-consideration, or sold to
multiple stakeholders.

## Research Questions

1. Can each stakeholder understand what the company sells?
2. What evidence makes the company look credible or unserious?
3. Can buyers find customer proof, case studies, or usage examples?
4. Can technical stakeholders find docs, implementation, and integration proof?
5. Can risk stakeholders find security, privacy, and compliance evidence?
6. Can the visitor identify the right next step: demo, contact sales, docs,
   pricing, or internal sharing?

## Recommended Personas

Use role-specific stakeholders rather than generic "enterprise user" personas:

- `economic-buyer`: evaluates value, credibility, pricing, and vendor risk
- `technical-evaluator`: checks docs, API, integrations, and feasibility
- `security-reviewer`: checks trust, compliance, data handling, and procurement
- `operations-owner`: checks workflow fit, onboarding, support, and reliability
- `executive-sponsor`: wants category clarity, strategic value, and customer
  proof

## Using An Existing EDSL AgentList

If your organization already has a buyer-panel `AgentList`, use it as the
source of truth. Export only the stakeholders relevant to the buying decision
you are studying.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="economic-buyer",
            traits={
                "role": "VP of insights",
                "budget_authority": "owns research software budget",
                "risk_tolerance": "medium",
                "decision_goal": "decide whether a demo is worth scheduling",
            },
            instruction=(
                "Looks for business value, customer proof, category clarity, "
                "pricing or procurement signals, and evidence that the company "
                "is serious enough for enterprise evaluation."
            ),
        ),
        Agent(
            name="security-reviewer",
            traits={
                "role": "security and privacy reviewer",
                "technical_depth": "medium",
                "decision_goal": "identify data, compliance, and vendor risk",
            },
            instruction=(
                "Looks for security, privacy, data handling, compliance, "
                "enterprise support, and vendor-review evidence."
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

Then reference those names in the fixture:

```yaml
personas:
  - economic-buyer
  - security-reviewer
```

For enterprise research, keep persona instructions specific to evidence
standards. A security reviewer and an economic buyer may both click "About,"
but they are looking for different proof.

## Basic Fixture

```yaml
id: acme-enterprise-buying
name: Acme Enterprise Buying
mode: live-site-enterprise-buying
comparison_title: Acme Enterprise Buying
comparison_output: acme-enterprise-buying.html
url_template: https://www.example.com/
study_title: Acme Enterprise Buying ({variant})
task: >
  You are evaluating whether this company is credible enough for an enterprise
  buying conversation. Find evidence about what the product does, who it is for,
  whether the company seems serious, and what next step you would take. Stop
  when you have enough evidence to recommend or reject scheduling a demo.
success_criteria: >
  The visitor finds enough product, credibility, proof, or risk evidence to
  decide whether scheduling a demo is reasonable.
personas:
  - economic-buyer
  - technical-evaluator
  - security-reviewer
runs_per_persona: 1
driver: edsl
max_steps: 10
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
examples/<site_or_product>/enterprise-buying.yaml
```

For public live sites, keep `max_concurrent_runs` at `1` or `2` unless you have
permission to generate more traffic. Enterprise buying studies often open menus,
docs, and support pages, so they can create more requests than a single-page
copy scan.

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/enterprise-buying.yaml
```

The command will run each persona/device variant, capture screenshots and
browser traces, ask EDSL for each browser decision, evaluate report-only checks,
and generate the comparison report.

Open:

```text
uxtest_store/comparisons/acme-enterprise-buying.html
```

Then inspect the detailed log for each study:

```text
uxtest_store/studies/<study-id>/analysis/log.html
```

## What To Inspect

Inspect:

- whether the first screen communicates category and seriousness
- which proof points each persona seeks
- whether evidence is concrete or vague
- whether docs/security/pricing/customer proof are findable
- whether demo/contact paths appear before or after sufficient confidence
- whether mobile hides trust or proof content
- final recommendation: schedule demo, keep researching, or reject

## Evidence Categories

Track findings by stakeholder concern:

- Product clarity: what it does, for whom, and in what workflow.
- Company credibility: team, customers, funding, activity, polish, and support.
- Technical feasibility: docs, examples, API, integrations, architecture.
- Risk readiness: privacy, security, compliance, data handling.
- Commercial readiness: pricing, procurement path, demo/contact, support.

## How To Interpret Results

Read each trace as a buying investigation, not as a simple pass/fail test.
Important moments are:

1. **Category formation**
   Did the visitor understand what kind of product or company this is?

2. **Trust search**
   What did they treat as credibility evidence: customers, team, docs,
   examples, security, polish, activity, or social proof?

3. **Evidence gap**
   What did they explicitly look for and fail to find?

4. **Next-step threshold**
   Did they schedule a demo because they were confident, because it was the
   only visible path, or not at all?

5. **Stakeholder divergence**
   Did buyers, technical evaluators, and risk reviewers need different content
   routes?

The strongest finding is often a mismatch: one stakeholder finds enough proof
while another cannot find the evidence needed to move the deal forward.

## Optional Checks

```yaml
checks:
  - id: reaches_enterprise_next_step
    type: trace_contains
    text_any:
      - demo
      - contact sales
      - security
      - docs
      - customers
    description: Enterprise buyer should find at least one buying-evidence area.
```

For enterprise research, use checks as guardrails only. The qualitative path and
reasoning are usually the most valuable output.

## Common Findings

- The product is interesting but the company does not look enterprise-ready.
- Demo CTA is visible before the page earns enough trust.
- Security and procurement evidence are missing or buried.
- Technical proof exists but is disconnected from buyer pages.
- Case studies or examples are too generic.
- Different stakeholders choose different routes with no clear cross-linking.
- Mobile pages show less proof before the conversion ask.

## Narrative Report Shape

1. Summary: whether enterprise visitors found enough evidence to continue.
2. Context: buying situation and stakeholder roles.
3. Method: personas, devices, URL, and EDSL/Playwright method.
4. Evidence found: product, proof, technical, risk, and commercial evidence.
5. Evidence missing: what blocked confidence.
6. Stakeholder differences: how roles diverged.
7. Conclusions: buyer-readiness implications.
8. Follow-on steps: content, IA, trust, demo path, and targeted stakeholder
   studies.

## Example Narrative Summary

Use a style like this:

```text
This enterprise buying study tested whether first-time enterprise stakeholders
could learn enough from the site to justify scheduling a demo. The economic
buyer understood the product category and found a visible demo path, but the
security reviewer and technical evaluator needed stronger proof before
recommending next steps. The main gap was not the presence of a CTA; it was the
lack of findable enterprise evidence near the decision path. The next design
step is to connect demo-oriented pages with security, documentation, customer
proof, and implementation examples so different buying roles can build
confidence without leaving the flow.
```

## Optional Human Screenshot Validation

After a synthetic enterprise study, export screenshots to an EDSL human survey
when you want real respondents to judge credibility or next-step confidence:

```bash
uv run uxtest humanize-export <study-id> \
  --template credibility \
  --screenshots representative \
  --max-screenshots 8 \
  --output ./humanize/jobs.ep
```

Inspect the generated Jobs package before creating the survey:

```bash
ep inspect ./humanize/jobs.ep
ep humanize create --jobs ./humanize/jobs.ep --scenario_method ordered --schema ./humanize/humanize_schema.json
```

Use human validation for questions such as:

- Does this page look credible enough for a first enterprise conversation?
- What proof is missing before you would share this internally?
- Which next step would you take from this screenshot?

The exported schema uses EDSL `humanize_schema` and survey-level
`custom_css`, so screenshot size and layout can be adjusted before launch.

## Follow-On Studies

Enterprise buying research usually leads to:

- Content comprehension: can stakeholders explain the offer and value?
- Information architecture: can they find security, docs, pricing, and support?
- Conversion path testing: can qualified visitors reach the right demo/contact
  route?
- Competitive benchmarking: do competitors provide stronger enterprise proof?
- Figma design study: do proposed trust or enterprise pages solve the evidence
  gap before implementation?
