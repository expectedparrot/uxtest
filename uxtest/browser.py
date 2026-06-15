from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def capture_state(page: Any, run_dir: Path, step: int, config: dict[str, Any]) -> dict[str, Any]:
    screenshot_rel = None
    if config.get("screenshot", "full") != "off":
        suffix = "jpg" if config.get("screenshot_format") == "jpeg" else "png"
        screenshot_rel = f"screenshots/step-{step:03d}.{suffix}"
        screenshot_path = run_dir / screenshot_rel
        kwargs: dict[str, Any] = {"path": str(screenshot_path), "full_page": False}
        if suffix == "jpg":
            kwargs["quality"] = int(config.get("screenshot_quality", 80))
            kwargs["type"] = "jpeg"
        page.screenshot(**kwargs)

    elements = page.evaluate(
        """
        () => {
          document.querySelectorAll('[data-uxtest-ref]').forEach((el) => el.removeAttribute('data-uxtest-ref'));
          const nearestLandmark = (el) => {
            const landmark = el.closest('nav,header,main,footer,aside,[role="navigation"],[role="banner"],[role="main"]');
            if (!landmark) return '';
            return (landmark.getAttribute('aria-label') || landmark.getAttribute('role') || landmark.tagName || '').toLowerCase();
          };
          const rawLabelFor = (el) => {
            const aria = (el.getAttribute('aria-label') || '').trim();
            if (aria) return { label: aria, source: 'aria-label' };
            const title = (el.getAttribute('title') || '').trim();
            if (title) return { label: title, source: 'title' };
            const alt = (el.querySelector('img[alt]')?.getAttribute('alt') || '').trim();
            if (alt) return { label: alt, source: 'img-alt' };
            const svgTitle = (el.querySelector('svg title')?.textContent || '').trim();
            if (svgTitle) return { label: svgTitle, source: 'svg-title' };
            const text = (el.innerText || '').trim();
            if (text) return { label: text, source: 'innerText' };
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            if (placeholder) return { label: placeholder, source: 'placeholder' };
            const value = (el.value || '').trim();
            if (value) return { label: value, source: 'value' };
            const name = (el.getAttribute('name') || '').trim();
            if (name) return { label: name, source: 'name' };
            if (el.tagName.toLowerCase() === 'button') {
              const landmark = nearestLandmark(el);
              const expanded = el.getAttribute('aria-expanded');
              if (expanded !== null || landmark.includes('nav') || landmark.includes('header') || landmark.includes('banner')) {
                return { label: 'Menu', source: 'inferred-menu-button' };
              }
              return { label: 'Unlabeled button', source: 'inferred-unlabeled-button' };
            }
            return { label: '', source: '' };
          };
          const contextFor = (el, label) => {
            const elRect = el.getBoundingClientRect();
            const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
              .map((heading) => ({ text: (heading.innerText || '').replace(/\\s+/g, ' ').trim(), rect: heading.getBoundingClientRect() }))
              .filter((heading) => heading.text && heading.rect.bottom <= elRect.top && heading.rect.right > elRect.left && heading.rect.left < elRect.right)
              .sort((a, b) => b.rect.bottom - a.rect.bottom);
            if (headings.length > 0) {
              return headings[0].text;
            }
            let current = el.parentElement;
            for (let depth = 0; current && depth < 5; depth += 1, current = current.parentElement) {
              const text = (current.innerText || '').replace(/\\s+/g, ' ').trim();
              if (!text || text === label || text.length > 500) continue;
              return text.slice(0, 240);
            }
            return '';
          };
          const nodes = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role="button"],[role="link"]'))
            .filter((el) => {
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              const inViewport = rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
              return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0 && inViewport;
            });
          return nodes.slice(0, 80).map((el, index) => {
            const ref = `e${index + 1}`;
            el.setAttribute('data-uxtest-ref', ref);
            const labelInfo = rawLabelFor(el);
            const label = labelInfo.label;
            return {
              ref,
              tag: el.tagName.toLowerCase(),
              role: el.getAttribute('role') || '',
              type: el.getAttribute('type') || '',
              name: el.getAttribute('name') || '',
              value: el.value || '',
              label,
              label_source: labelInfo.source,
              context: contextFor(el, label),
              selector_hint: `[data-uxtest-ref="${ref}"]`
            };
          });
        }
        """
    )
    visible_text = page.evaluate(
        """
        () => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          const chunks = [];
          while (walker.nextNode()) {
            const node = walker.currentNode;
            const text = (node.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!text) continue;
            const parent = node.parentElement;
            if (!parent) continue;
            const style = window.getComputedStyle(parent);
            if (style.visibility === 'hidden' || style.display === 'none') continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            const rects = Array.from(range.getClientRects());
            range.detach();
            if (rects.some((rect) => rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth)) {
              chunks.push(text);
            }
          }
          return chunks.join('\\n');
        }
        """
    )
    headings = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
          .map((el) => {
            const rect = el.getBoundingClientRect();
            return {
              text: (el.innerText || '').replace(/\\s+/g, ' ').trim(),
              level: el.tagName.toLowerCase(),
              in_viewport: rect.bottom > 0 && rect.top < window.innerHeight,
              y: Math.round(rect.top + window.scrollY)
            };
          })
          .filter((item) => item.text)
          .slice(0, 80)
        """
    )
    return {
        "url": page.url,
        "page_title": page.title(),
        "screenshot": screenshot_rel,
        "interactive_elements": elements,
        "headings": headings,
        "visible_text": visible_text[:6000],
    }


def execute_action(page: Any, state_or_action: Any, action: Any | None = None) -> dict[str, Any]:
    action = action or state_or_action
    before_snapshot = page_action_snapshot(page)
    try:
        before_url = page.url
        if action.type == "none":
            return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True)
        if action.type == "wait":
            page.wait_for_timeout(750)
            return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True)
        if action.type == "back":
            page.go_back(wait_until="networkidle")
            return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True)
        if action.type == "scroll":
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(300)
            return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True)
        if action.type == "find":
            found = find_text_on_page(page, action.text or action.value or "")
            page.wait_for_timeout(300)
            return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True, found=found)
        if not action.ref:
            return _action_result(
                action.type,
                before_snapshot,
                page_action_snapshot(page),
                ok=False,
                error=f"Action {action.type} requires ref.",
            )
        locator = page.locator(f'[data-uxtest-ref="{action.ref}"]').first
        if action.type == "click":
            locator.click(timeout=5000)
        elif action.type == "type":
            locator.fill(action.value or action.text or "", timeout=5000)
        elif action.type == "select":
            locator.select_option(action.value or action.text or "", timeout=5000)
        wait_after_action(page, before_url)
        return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=True)
    except Exception as exc:
        return _action_result(action.type, before_snapshot, page_action_snapshot(page), ok=False, error=str(exc))


def page_action_snapshot(page: Any) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "url": safe_page_url(page),
        "open_pages": safe_open_pages(page),
        "text_hash": "",
        "interactive_hash": "",
        "expanded_count": 0,
        "menu_like_count": 0,
        "scroll_y": 0,
    }
    try:
        dom = page.evaluate(
            """
            () => {
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
              };
              const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 20000);
              const interactive = Array.from(document.querySelectorAll('a,button,input,select,textarea,[role="button"],[role="link"],[role="menuitem"]'))
                .filter(visible)
                .slice(0, 120)
                .map((el) => [
                  el.tagName.toLowerCase(),
                  el.getAttribute('role') || '',
                  el.getAttribute('aria-expanded') || '',
                  el.getAttribute('aria-label') || '',
                  el.getAttribute('href') || '',
                  el.value || '',
                  (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120)
                ].join('|'))
                .join('\\n');
              const expandedCount = Array.from(document.querySelectorAll('[aria-expanded="true"],details[open]')).filter(visible).length;
              const menuLikeCount = Array.from(document.querySelectorAll('[role="menu"],[role="menuitem"],[role="listbox"],[aria-expanded="true"],details[open]')).filter(visible).length;
              return { text, interactive, expandedCount, menuLikeCount, scrollY: Math.round(window.scrollY || 0) };
            }
            """
        )
        if isinstance(dom, dict):
            snapshot.update(
                {
                    "text_hash": short_digest(str(dom.get("text") or "")),
                    "interactive_hash": short_digest(str(dom.get("interactive") or "")),
                    "expanded_count": int(dom.get("expandedCount") or 0),
                    "menu_like_count": int(dom.get("menuLikeCount") or 0),
                    "scroll_y": int(dom.get("scrollY") or 0),
                }
            )
    except Exception:
        pass
    return snapshot


def safe_page_title(page: Any) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def safe_page_url(page: Any) -> str:
    try:
        return str(page.url)
    except Exception:
        return ""


def safe_open_pages(page: Any) -> int:
    try:
        return len(page.context.pages)
    except Exception:
        return 0


def short_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16] if value else ""


def classify_action_outcome(action_type: str, before: dict[str, Any], after: dict[str, Any], *, ok: bool, **extra: Any) -> dict[str, Any]:
    before_url = str(before.get("url") or "")
    after_url = str(after.get("url") or "")
    before_open_pages = int(before.get("open_pages") or 0)
    after_open_pages = int(after.get("open_pages") or 0)

    if not ok:
        outcome = "failed_action"
    elif action_type == "none":
        outcome = "none"
    elif after_open_pages > before_open_pages:
        outcome = "new_tab"
    elif before_url != after_url:
        outcome = "hash_change" if without_fragment(before_url) == without_fragment(after_url) else "url_navigation"
    elif action_type == "wait":
        outcome = "wait"
    elif action_type == "scroll":
        outcome = "scroll"
    elif action_type == "find":
        outcome = "find_found" if extra.get("found") else "find_not_found"
    elif action_type in {"type", "select"}:
        outcome = "form_change" if snapshot_content_changed(before, after) else "no_visible_change"
    elif int(after.get("expanded_count") or 0) > int(before.get("expanded_count") or 0) or int(after.get("menu_like_count") or 0) > int(before.get("menu_like_count") or 0):
        outcome = "menu_opened"
    elif int(after.get("expanded_count") or 0) < int(before.get("expanded_count") or 0) or int(after.get("menu_like_count") or 0) < int(before.get("menu_like_count") or 0):
        outcome = "menu_closed"
    elif snapshot_content_changed(before, after):
        outcome = "same_page_state_change"
    elif int(before.get("scroll_y") or 0) != int(after.get("scroll_y") or 0):
        outcome = "scroll_position_change"
    else:
        outcome = "no_visible_change"

    return {
        "action_outcome": outcome,
        "state_change": outcome
        in {
            "url_navigation",
            "hash_change",
            "new_tab",
            "menu_opened",
            "menu_closed",
            "same_page_state_change",
            "scroll_position_change",
            "form_change",
            "scroll",
            "find_found",
        },
        "url_change_type": url_change_type(before_url, after_url),
        "open_pages_delta": after_open_pages - before_open_pages,
    }


def snapshot_content_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before.get("text_hash") != after.get("text_hash") or before.get("interactive_hash") != after.get("interactive_hash")


def without_fragment(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def url_change_type(before_url: str, after_url: str) -> str:
    if before_url == after_url:
        return "none"
    if without_fragment(before_url) == without_fragment(after_url):
        return "hash"
    before = urlsplit(before_url)
    after = urlsplit(after_url)
    if (before.scheme, before.netloc) != (after.scheme, after.netloc):
        return "external"
    if before.path != after.path:
        return "path"
    return "query"


def find_text_on_page(page: Any, text: str) -> bool:
    target = re.sub(r"\s+", " ", text).strip()
    if not target:
        return False
    return bool(
        page.evaluate(
            """
            (target) => {
              const needle = target.toLowerCase();
              const candidates = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,a,button,p,li,dt,dd,div,section,article'))
                .filter((el) => {
                  const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                  if (!text || !text.toLowerCase().includes(needle)) return false;
                  const style = window.getComputedStyle(el);
                  return style.visibility !== 'hidden' && style.display !== 'none';
                })
                .sort((a, b) => {
                  const ah = /^H[1-6]$/.test(a.tagName) ? 0 : 1;
                  const bh = /^H[1-6]$/.test(b.tagName) ? 0 : 1;
                  if (ah !== bh) return ah - bh;
                  return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
                });
              const found = candidates[0];
              if (!found) {
                return window.find(target, false, false, true, false, true, false);
              }
              found.scrollIntoView({ block: 'center', inline: 'nearest' });
              return true;
            }
            """,
            target,
        )
    )


def settle_page(page: Any) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=2000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(150)


def wait_after_action(page: Any, before_url: str) -> None:
    try:
        page.wait_for_function("url => window.location.href !== url", arg=before_url, timeout=3000)
    except Exception:
        pass
    settle_page(page)


def _action_result(action_type: str, before: dict[str, Any], after: dict[str, Any], *, ok: bool, **extra: Any) -> dict[str, Any]:
    classification = classify_action_outcome(action_type, before, after, ok=ok, **extra)
    result = {
        "ok": ok,
        "navigation": before.get("url") != after.get("url"),
        "console_errors": 0,
        "final_url": after.get("url"),
        **classification,
    }
    result.update(extra)
    return result
