# John Horton Academic Website Study Design

## Goal

Evaluate whether first-time visitors can quickly understand John J. Horton's
academic identity, find relevant work, and decide on a reasonable next action.

The site is a dense academic homepage: bio first, then a long research section
with papers, versions, citations, slides, media, awards, grants, and talks.
This study should test scanning, orientation, link choice, credibility, and
mobile readability rather than checkout-style conversion.

## Research Questions

- Can visitors understand the main research areas from the first screen?
- Can they find work related to AI, labor markets, market design, or online
  platforms without using browser search?
- Do link labels like `jjh`, `arxiv`, `nber`, `gs`, `slides`, and `media` make
  sense to non-academic visitors?
- Does the long single-page structure help or hurt task completion on mobile?
- Can visitors infer a next action: read a paper, open slides, cite the work,
  invite the person, contact him, or share the profile?
- Which visitor types need summaries, filters, dates, topic grouping, or
  stronger contact/navigation cues?

## Personas

- `prospective-phd-student`: wants research fit and advising signals.
- `research-collaborator`: wants recent papers, coauthors, status, and code or
  slides.
- `journalist-policy-analyst`: wants plain-language expertise, media links, and
  quotable/current work.
- `conference-organizer`: wants credibility, topic fit, recent talks, and an
  invitation decision.

## Task

Starting from `https://john-joseph-horton.com/`, decide whether John J. Horton is
relevant to your goal. Find the most useful next thing you would click or read,
explain what you learned, and call out anything confusing or hard to use.

## Success Criteria

A run is successful when the visitor identifies a relevant paper, research
topic, talk, media item, or contact/collaboration signal and can explain a
reasonable next action.

## Evidence To Capture

- First click or first scroll direction.
- Whether the visitor starts with bio, research, talks, or external links.
- Which link labels are understood or misunderstood.
- Whether the visitor uses on-page scanning or browser find behavior.
- Whether mobile users can recover from the long research list.
- Any moment where the visitor cannot tell whether an item is current, important,
  downloadable, or intended for them.

## Run

```bash
uv run uxtest ci examples/jjh_site/discovery.yaml
```

The fixture runs desktop and iPhone-sized variants with four personas. It uses
limited batching with `max_concurrent_runs: 2` so the site is not hit by a large
burst of simultaneous sessions.

After the run, inspect:

- `.uxtest/comparisons/jjh-academic-site-discovery.html`
- each study's `analysis/log.html`
- each study's `analysis/uxr_report.html`
- each study's generated GIF index from `uxtest animate`
