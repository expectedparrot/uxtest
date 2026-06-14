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
variants:
  - name: desktop
    device: desktop
  - name: mobile
    device: iphone
```

## What To Inspect

Inspect:

- search terms or `find` text the agent uses
- whether it opens docs, resources, product menus, or footer links
- whether feature mentions are concrete or vague
- whether the agent confuses adjacent features
- screenshots of evidence pages
- final reasoning about confidence

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
