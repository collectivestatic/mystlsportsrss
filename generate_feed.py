#!/usr/bin/env python3
"""
Generates an RSS feed for St. Louis Cardinals game outcomes and news,
plus St. Louis CITY SC (first team) news.

Data sources:
  - CITY SC official website news: scraped from stlcitysc.com's "Team" topic
    page, which is the site's own first-team-only category (excludes CITY2,
    Academy, Community, Stadium, eMLS content) — no feed available, HTML scrape.
  - St. Louis Magazine Sports section: scraped and keyword-filtered for
    Cardinals/City SC mentions, since the section covers all STL teams and
    has no RSS feed of its own.

Note: stlcitysc.com and stlmag.com don't expose article publish dates in
their listing markup, so items from those two sources use the time they
were first scraped as their pubDate. That's a reasonable proxy for a feed
that runs on a timer, but it means dates reflect "when this scraper first
saw it," not necessarily the original publish date.

Run this on a timer (see .github/workflows/update-feed.yml) to keep
feed.xml up to date automatically.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

# ---- Config -----------------------------------------------------------

NEWS_LIMIT = 5                # max articles pulled per news source, per team

CITYSC_NEWS_URL = "https://www.stlcitysc.com/news/topics/team"  # first-team-only topic page
STLMAG_SPORTS_URL = "https://www.stlmag.com/news/sports/"       # mixed STL sports section, needs filtering

# Keywords used to filter STL Magazine's general Sports section down to
# Cardinals / City SC content only. Update these if you start missing
# articles (e.g. a headline that only uses a player's name).
STLMAG_KEYWORDS = [
    "cardinals", "cards",
    "city sc", "st. louis city", "stl city", "citysc",
]

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mystlsportsrss/1.0)"}

FEED_TITLE = "STL Cardinals & City SC News"
# IMPORTANT: this must match your actual GitHub Pages URL,
# e.g. https://yourusername.github.io/your-repo/feed.xml
FEED_LINK = "https://collectivestatic.github.io/mystlsportsrss/feed.xml"
FEED_DESCRIPTION = "Auto-updated Cardinals game outcomes and Cardinals/City SC news"

REQUEST_TIMEOUT = 15  # seconds


# ---- Helpers ------------------------------------------------------------

def _parse_iso(value, formats):
    """Try a list of strptime formats, return the first that parses."""
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {value}")


def _matches_team(article, keywords):
    """Check if a news article mentions any of the given keywords."""
    haystack = " ".join([
        article.get("headline", ""),
        article.get("description", ""),
    ]).lower()
    return any(kw.lower() in haystack for kw in keywords)



# ---- Cardinals league news (ESPN, filtered) ------------------------------

def get_cardinals_news(limit=NEWS_LIMIT):
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news"
    items = []
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Cardinals News] fetch failed: {e}")
        return items

    for article in data.get("articles", []):
        if not _matches_team(article, ["cardinals"]):
            continue
        try:
            headline = article["headline"]
            description = article.get("description", "")
            link = article.get("links", {}).get("web", {}).get("href", FEED_LINK)
            pub_date = _parse_iso(article["published"], ["%Y-%m-%dT%H:%M:%SZ"])

            items.append({
                "title": f"Cardinals News: {headline}",
                "description": description or headline,
                "pub_date": pub_date,
                "guid": f"cardinals-news-{article.get('id', headline)}",
                "link": link,
            })
        except (KeyError, ValueError) as e:
            print(f"[Cardinals News] skipping malformed article: {e}")
            continue
        if len(items) >= limit:
            break

    print(f"[Cardinals News] parsed {len(items)} articles")
    return items



# ---- CITY SC official website news (scraped, first team only) -----------

def get_citysc_website_news(limit=NEWS_LIMIT):
    """Scrapes stlcitysc.com's "Team" news topic page.

    stlcitysc.com has no RSS feed, so this is an HTML scrape. The site
    itself categorizes news into topics (Team, CITY2, Academy, Stadium,
    Community, eMLS, Soccer 101) — pointing at the "Team" topic page
    gets first-team news for free, without needing keyword filtering to
    exclude the reserve/academy/community content.

    NOTE: the listing page doesn't expose per-article publish dates in
    its markup, so pub_date falls back to "now" (time of scrape). If
    stlcitysc.com changes its page structure, this may need updated
    selectors — it's a plain <a href> scan filtered to /news/ links.
    """
    items = []
    try:
        resp = requests.get(CITYSC_NEWS_URL, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        resp.raise_for_status()
        # Use raw bytes (resp.content), not resp.text — requests sometimes
        # mis-guesses the charset when a site's headers don't declare one
        # cleanly, which corrupts non-ASCII characters (e.g. "Â" showing up
        # in place of a non-breaking space). BeautifulSoup auto-detects
        # encoding from the bytes/meta tags more reliably.
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        print(f"[CITY SC Website] fetch failed: {e}")
        return items

    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/"):
            href = "https://www.stlcitysc.com" + href
        if not href.startswith("https://www.stlcitysc.com/news/"):
            continue
        # Skip nav/category links (topics index, "all news", "latest news", bare /news)
        tail = href[len("https://www.stlcitysc.com/news/"):].strip("/")
        if tail == "" or tail.startswith("topics") or tail.startswith("all") or tail.startswith("latest") or tail.startswith("index"):
            continue

        # Prefer the <a title="..."> attribute — it holds the clean
        # headline. The visible link text works for most cards, but the
        # site's featured top story wraps the teaser paragraph into the
        # same <a>, which would otherwise run headline + teaser together.
        title = (a.get("title") or "").strip() or a.get_text(strip=True)
        title = title[:200]  # safety cap in case a future card also lacks a clean title attr
        if not title or href in seen_links:
            continue
        seen_links.add(href)

        items.append({
            "title": f"CITY SC News: {title}",
            "description": title,
            "pub_date": datetime.now(timezone.utc),
            "guid": f"citysc-web-{href}",
            "link": href,
        })
        if len(items) >= limit:
            break

    print(f"[CITY SC Website] parsed {len(items)} articles")
    return items


# ---- St. Louis Magazine Sports (scraped, keyword-filtered) ---------------

def get_stlmag_sports_news(limit=NEWS_LIMIT):
    """Scrapes St. Louis Magazine's Sports section, filtered by keyword.

    stlmag.com has no RSS feed either, and unlike stlcitysc.com, its
    Sports section isn't split by team — it mixes Cardinals, City SC,
    Blues, and general STL sports content together. STLMAG_KEYWORDS
    filters link text down to articles that plausibly mention the
    Cardinals or City SC. This is a blunt keyword match on the visible
    link text only (no article body), so it will miss articles that
    reference a team only by player name, and may need STLMAG_KEYWORDS
    tuned over time.

    NOTE: like the CITY SC scraper above, no publish date is exposed in
    the listing markup, so pub_date falls back to scrape time.
    """
    items = []
    try:
        resp = requests.get(STLMAG_SPORTS_URL, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")  # see CITY SC scraper comment on why not resp.text
    except Exception as e:
        print(f"[STL Mag Sports] fetch failed: {e}")
        return items

    seen_links = set()
    for a in soup.find_all("a", href=True):
        title = (a.get("title") or "").strip() or a.get_text(strip=True)
        title = title[:200]
        if not title or len(title) < 8:
            continue
        if not _matches_team({"headline": title, "description": ""}, STLMAG_KEYWORDS):
            continue

        href = a["href"]
        if href.startswith("/"):
            href = "https://www.stlmag.com" + href
        if not href.startswith("https://www.stlmag.com/"):
            continue
        if href in seen_links:
            continue
        seen_links.add(href)

        items.append({
            "title": f"STL Mag: {title}",
            "description": title,
            "pub_date": datetime.now(timezone.utc),
            "guid": f"stlmag-{href}",
            "link": href,
        })
        if len(items) >= limit:
            break

    print(f"[STL Mag Sports] parsed {len(items)} matching articles")
    return items


# ---- RSS building --------------------------------------------------------

def build_rss(items):
    items.sort(key=lambda x: x["pub_date"])

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = FEED_LINK
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))

    for item in items:
        item_el = ET.SubElement(channel, "item")
        ET.SubElement(item_el, "title").text = item["title"]
        ET.SubElement(item_el, "description").text = item["description"]
        ET.SubElement(item_el, "link").text = item["link"]
        ET.SubElement(item_el, "guid", isPermaLink="false").text = item["guid"]
        ET.SubElement(item_el, "pubDate").text = format_datetime(item["pub_date"])

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")  # requires Python 3.9+
    tree.write("feed.xml", encoding="UTF-8", xml_declaration=True)
    print(f"Wrote feed.xml with {len(items)} total items")


def main():
    items = (
        get_citysc_website_news()
        + get_stlmag_sports_news()
    )
    build_rss(items)


if __name__ == "__main__":
    main()
