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

## Using An Existing EDSL AgentList

If you already have an EDSL `AgentList`, export personas whose expectations
about labels and content locations differ. IA research is strongest when the
personas have different mental models of where the same information should live.

Example:

```python
from pathlib import Path

import yaml
from edsl import Agent, AgentList


agents = AgentList(
    [
        Agent(
            name="security-reviewer",
            traits={
                "role": "security reviewer",
                "target_content": "security, privacy, compliance, trust",
                "expected_locations": ["security", "trust center", "docs", "footer"],
                "domain_familiarity": "high",
            },
            instruction=(
                "Looks first for security, trust, privacy, compliance, docs, "
                "or footer routes. Notices overloaded labels."
            ),
        ),
        Agent(
            name="developer-integrator",
            traits={
                "role": "developer integrator",
                "target_content": "API, docs, examples, integrations",
                "expected_locations": ["docs", "developers", "resources", "github"],
                "domain_familiarity": "high",
            },
            instruction=(
                "Looks for docs, developer routes, examples, API references, "
                "SDKs, GitHub, or integration pages."
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

Then reference the exported personas:

```yaml
personas:
  - security-reviewer
  - developer-integrator
```

Keep the target content precise. "Find anything useful" produces weak IA
evidence; "find SOC 2 or data privacy information" produces actionable label
and grouping evidence.

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

Save this as:

```text
examples/<site_or_product>/information-architecture.yaml
```

## How To Run

From the package root:

```bash
uv run uxtest ci examples/<site_or_product>/information-architecture.yaml
```

Open the comparison report:

```text
.uxtest/comparisons/acme-security-ia.html
```

Then inspect individual logs:

```text
.uxtest/studies/<study-id>/analysis/log.html
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

## How To Interpret Results

IA studies are about expectation mismatch. A run can reach the right content
and still reveal a bad label if it required repeated guesses.

Read traces for:

1. **Expected location**
   Where did the persona look first, and why?

2. **Label interpretation**
   What did labels such as "Resources," "Products," "Learn," "Docs," or
   "Support" mean to the visitor?

3. **Grouping mismatch**
   Did content live under a category that made sense to the company but not to
   the visitor?

4. **Recovery behavior**
   Did the visitor use page scanning, footer links, browser find, search, or
   repeated menu openings?

5. **Evidence recognition**
   Did they know when they had found the target content, or was the page label
   stronger than the substance?

6. **Device effect**
   Did mobile reorder, hide, or collapse the path enough to change behavior?

The best recommendations usually name the label or grouping change, not just
"make X easier to find."

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

## Example Narrative Summary

Use a style like this:

```text
This information architecture study tested whether visitors could find security
and compliance evidence from the homepage. Desktop visitors usually opened
Resources or the footer before finding relevant material, while mobile visitors
spent more steps in collapsed navigation. The main IA issue is that the site has
trust evidence, but it is not grouped under the labels risk reviewers expect.
"Resources" reads as educational content, not vendor-review evidence. The next
step is to add a clearer Trust or Security route and cross-link it from demo,
docs, and enterprise pages.
```

## Optional Human Screenshot Validation

Use EDSL human validation when you want real respondents to choose where they
would look for target content from screenshots:

```bash
uv run uxtest humanize-export <study-id> \
  --template information-architecture \
  --screenshots representative \
  --max-screenshots 8
```

Review and launch the generated survey:

```bash
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py
uv run python .uxtest/studies/<study-id>/analysis/humanize_survey.py --launch
```

Useful human questions include:

- Where would you click first to find this information?
- Which label best matches the target content?
- Does this page contain enough evidence for the target question?

The generated survey uses EDSL `humanize_schema` and `custom_css`, so screenshot
size and answer layout can be edited before launch.

## Follow-On Studies

Information architecture studies usually lead to:

- Feature findability: can visitors determine whether a specific capability
  exists?
- Conversion path testing: can visitors reach the target action after IA
  changes?
- Content comprehension: do new labels communicate the right meaning?
- Longitudinal regression: did nav changes improve findability without breaking
  other paths?
