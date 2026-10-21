"""Website crawl: headless Chromium renders each page, trafilatura extracts the text.

A pure scrape. Up to MAX_PAGES same-domain pages, with pages that describe the organization
(about, team, mission, impact...) promoted to the front of the queue. No screenshots, no
interpretation of what was read. Needs `playwright install chromium` once.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup

MAX_PAGES = 10
NAV_TIMEOUT_MS = 25_000
SETTLE_TIMEOUT_MS = 8_000
VIEWPORT = {"width": 1280, "height": 900}
MAX_CHARS_PER_PAGE = 15_000
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0 Safari/537.36 nonprofit-backpack/0.1")
PRIORITY_PATHS = ("about", "team", "people", "leadership", "board", "trustee", "staff", "who-we-are",
                  "what-we-do", "our-work", "program", "impact", "results", "mission", "vision", "history",
                  "annual-report", "financial")
SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".mp4", ".mp3", ".css", ".js", ".xml")
SKIP_FRAMES = ("stripe", "recaptcha", "google", "facebook", "twitter", "youtube", "doubleclick", "hotjar", "intercom")


@dataclass
class Page:
    url: str
    title: str
    text: str


class ScrapeError(Exception):
    pass


def _host_is_private(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    return any(ipaddress.ip_address(i[4][0]).is_private or ipaddress.ip_address(i[4][0]).is_loopback
               or ipaddress.ip_address(i[4][0]).is_link_local or ipaddress.ip_address(i[4][0]).is_reserved for i in infos)


def check_url_allowed(url: str) -> str | None:
    """An error string if the URL must not be fetched (SSRF guard), else None."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return f"unsupported scheme: {p.scheme or '(none)'}"
    if not p.hostname:
        return "no hostname"
    if _host_is_private(p.hostname):
        return "host resolves to a private or unresolvable address"
    return None


def _same_domain_links(html: str, base_url: str) -> list[str]:
    base = urlparse(base_url)
    seen: list[str] = []
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#", 1)[0]
        p = urlparse(href)
        if p.scheme not in ("http", "https") or p.hostname != base.hostname:
            continue
        if p.path in ("", "/") and not p.query:
            href = f"{p.scheme}://{p.hostname}/"
        if href.lower().endswith(SKIP_EXT):
            continue
        if href not in seen:
            seen.append(href)
    return sorted(seen, key=lambda u: (not any(k in urlparse(u).path.lower() for k in PRIORITY_PATHS), seen.index(u)))


def _domain_variant(url: str) -> str | None:
    host = urlparse(url).hostname or ""
    alt = host[4:] if host.startswith("www.") else f"www.{host}"
    return url.replace(f"//{host}", f"//{alt}", 1) if "." in alt else None


def _auto_scroll(page) -> None:
    """Step down the page so lazy-loaded content mounts. Best effort."""
    try:
        height, pos = page.evaluate("document.body.scrollHeight"), 0
        while pos < min(height, 30_000):
            pos += VIEWPORT["height"]
            page.evaluate(f"window.scrollTo(0, {pos})")
            page.wait_for_timeout(150)
            height = page.evaluate("document.body.scrollHeight")
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
    except Exception:
        pass


def _frame_texts(page) -> str:
    """Text inside embedded widget iframes, which page.content() does not include."""
    parts = []
    for f in page.frames[1:]:
        if any(s in (f.url or "") for s in SKIP_FRAMES):
            continue
        try:
            t = f.inner_text("body", timeout=2500).strip()
        except Exception:
            continue
        if len(t) > 80:
            parts.append(t[:8000])
    return "\n\n".join(parts)


def _render(page, url: str) -> tuple[str, str, str] | None:
    """(html, title, embedded frame text) or None on failure."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
        except Exception:
            pass
        _auto_scroll(page)
        if _host_is_private(urlparse(page.url).hostname or ""):
            return None
        return page.content(), page.title(), _frame_texts(page)
    except Exception:
        return None


def _extract(html: str, url: str, embeds: str) -> str:
    text = trafilatura.extract(html, url=url, include_links=False, include_comments=False, favor_recall=True) or ""
    if embeds:
        text += "\n\nEmbedded widget content:\n" + embeds
    return text.strip()[:MAX_CHARS_PER_PAGE]


def crawl(url: str, max_pages: int = MAX_PAGES, on_page=None) -> list[Page]:
    """Render the start page and up to max_pages-1 same-domain pages. Raises ScrapeError if nothing is readable.
    `on_page(i, max_pages, url)` is called before each page loads, for progress display."""
    notify = on_page or (lambda i, n, u: None)
    err = check_url_allowed(url)
    if err:
        raise ScrapeError(err)
    from playwright.sync_api import sync_playwright

    pages: list[Page] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            ctx = browser.new_context(viewport=VIEWPORT, user_agent=USER_AGENT)
            page = ctx.new_page()
            notify(1, max_pages, url)
            first = _render(page, url)
            if first is None:
                alt = _domain_variant(url)
                if alt and not check_url_allowed(alt):
                    url, first = alt, _render(page, alt)
            if first is None:
                raise ScrapeError(f"could not load {url}")
            html, title, embeds = first
            text = _extract(html, url, embeds)
            if text:
                pages.append(Page(page.url or url, title, text))
            for link in _same_domain_links(html, page.url or url):
                if len(pages) >= max_pages:
                    break
                if check_url_allowed(link) or any(p.url == link for p in pages):
                    continue
                notify(len(pages) + 1, max_pages, link)
                r = _render(page, link)
                if not r:
                    continue
                t = _extract(r[0], link, r[2])
                if t:
                    pages.append(Page(page.url or link, r[1], t))
        finally:
            browser.close()
    if not pages:
        raise ScrapeError(f"no readable text at {url}; the site may block automated browsers")
    return pages
