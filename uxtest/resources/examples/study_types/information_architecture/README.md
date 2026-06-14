# Information Architecture

## What This Study Answers

An information architecture study asks whether visitors can predict where
content should live and then find it. The target is usually not conversion
itself; it is whether labels, menus, grouping, search, and page hierarchy match
visitor expectations.

Use this study type to test whether visitors can find:

- pricing
- docs
- security or compliance information
- integrations
- examples or templates
- support
- product details
- API references
- case studies

## When To Use It

Run this when users say "I could not find X", when a site has grown many nav
items, or when a redesign changes labels and grouping. It is especially useful
for desktop/mobile comparisons because mobile menus often hide or reorder
important IA.

## Research Questions

1. Where does the visitor expect the content to be?
2. Which label or menu do they try first?
3. Do they use search, nav, page scanning, or `find` behavior?
4. Which labels are confused with each other?
5. Does the visitor recognize when they have found enough evidence?
6. Do mobile visitors find the same content as desktop visitors?

## Recommended Personas

Choose personas based on the content being sought. For example:

- `security-reviewer`: expects compliance, security, and privacy information
- `developer-integrator`: expects docs, API, SDK, examples, and GitHub links
- `buyer`: expects pricing, plans, procurement, and support
- `operator`: expects workflows, templates, support, and implementation details

Avoid personas whose goals are too broad. IA tasks work best when the target
content is specific.

## Basic Fixture

```yaml
id: acme-security-ia
name: Acme Security IA
mode: live-site-ia
comparison_title: Acme Security IA
comparison_output: acme-security-ia.html
url_template: https://www.example.com/
study_title: Acme Security IA ({variant})
task: >
  Starting from the homepage, find information that would help you evaluate
  security, privacy, or compliance. Stop when you find credible information or
  when you conclude the site does not make it findable.
success_criteria: >
  The visitor finds a security, privacy, compliance, trust, or documentation
  page with relevant evidence.
personas:
  - security-reviewer
  - enterprise-buyer
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

Inspect the trace for:

- first menu opened
- use of top nav vs footer vs page sections
- static headings the agent expected to click
- repeated menu openings without progress
- search/find behavior
- final page and whether it actually contains the target content
- differences between desktop and mobile navigation

## Optional Checks

If the desired destination is known:

```yaml
checks:
  - id: finds_security_content
    type: final_url
    url_contains_any:
      - security
      - trust
      - privacy
      - compliance
    description: Visitor should reach a security/trust content area.
```

Use final URL checks carefully. Some sites expose the evidence in modals,
expanded sections, PDFs, or external documentation.

## Common Findings

- Visitors look for content in a different top-level category than expected.
- Product menus mix buyer, user, and developer concepts.
- Mobile navigation hides secondary links that desktop visitors use.
- Footer links are findable only after repeated scrolling.
- Labels such as "Resources", "Learn", "Docs", and "Support" are overloaded.
- Search/find behavior succeeds where navigation fails.
- Visitors find a page with the right label but insufficient substance.

## Narrative Report Shape

1. Summary: whether target content was findable.
2. Context: why this information matters to the visitor.
3. Method: target content, personas, devices, and run count.
4. Navigation behavior: first guesses, menus, search/find, and detours.
5. Findability issues: label ambiguity, grouping, depth, or mobile gaps.
6. Conclusions: IA changes that would reduce friction.
7. Follow-on steps: nav label tests, content additions, and regression fixtures.
