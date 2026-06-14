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
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
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
