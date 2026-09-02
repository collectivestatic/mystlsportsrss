#!/usr/bin/env python3
"""
Generates an RSS feed for the St. Louis Cardinals schedules and news.

Data sources:
  - Cardinals schedule: MLB Stats API (statsapi.mlb.com) — free, no key
 
  - Cardinals/City SC league news: ESPN news endpoints, filtered by team — free, no key
  - Cardinals website news: MLB.com's official Cardinals RSS feed — free, no key


Run this on a timer (see .github/workflows/update-feed.yml) to keep
feed.xml up to date automatically.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

# ---- Config -----------------------------------------------------------

CARDINALS_TEAM_ID = 138       # St. Louis Cardinals (MLB Stats API team id)


DAYS_BEHIND = 3               # include recently completed games
DAYS_AHEAD = 14               # include upcoming games

NEWS_LIMIT = 5                # max articles pulled per news source, per team

FEED_TITLE = "STL Cardinals Schedule & News"
# IMPORTANT: this must match your actual GitHub Pages URL,
# e.g. https://yourusername.github.io/your-repo/feed.xml
FEED_LINK = "https://collectivestatic.github.io/mystlsportsrss/feed.xml"
FEED_DESCRIPTION = "Auto-updated schedule and news for the St. Louis Cardinals"

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


# ---- Cardinals schedule (MLB Stats API) ---------------------------------

def get_cardinals_games():
    start = (datetime.now(timezone.utc) - timedelta(days=DAYS_BEHIND)).strftime("%Y-%m-%d")
    end = (datetime.now(timezone.utc) + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&teamId={CARDINALS_TEAM_ID}&startDate={start}&endDate={end}"
    )

    items = []
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Cardinals] fetch failed: {e}")
        return items

    for date_block in data.get("dates", []):
        for game in date_block.get("games", []):
            try:
                away = game["teams"]["away"]["team"]["name"]
                home = game["teams"]["home"]["team"]["name"]
                status = game["status"]["detailedState"]
                game_dt = _parse_iso(game["gameDate"], ["%Y-%m-%dT%H:%M:%SZ"])

                is_home = home == "St. Louis Cardinals"
                opponent = away if is_home else home
                venue = "Home" if is_home else "Away"

                title = f"Cardinals ({venue}) vs {opponent} — {status}"
                description = f"{away} at {home}. Status: {status}."

                if status == "Final":
                    away_score = game["teams"]["away"].get("score")
                    home_score = game["teams"]["home"].get("score")
                    if away_score is not None and home_score is not None:
                        description += f" Final score: {away} {away_score} – {home_score} {home}."

                items.append({
                    "title": title,
                    "description": description,
                    "pub_date": game_dt,
                    "guid": f"cardinals-{game.get('gamePk')}",
                    "link": FEED_LINK,
                })
            except (KeyError, ValueError) as e:
                print(f"[Cardinals] skipping malformed game entry: {e}")
                continue

    print(f"[Cardinals] parsed {len(items)} games")
    return items


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



# ---- Cardinals official website news (MLB.com RSS) -----------------------

def get_cardinals_website_news(limit=NEWS_LIMIT):
    """Uses MLB.com's official Cardinals RSS feed."""
    url = "https://www.mlb.com/cardinals/feeds/news/rss.xml"
    items = []
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"[Cardinals Website] fetch failed: {e}")
        return items

    for item in root.findall("./channel/item"):
        try:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or FEED_LINK).strip()
            guid = (item.findtext("guid") or link).strip()
            pub_date_raw = (item.findtext("pubDate") or "").strip()

            pub_date = parsedate_to_datetime(pub_date_raw)
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)

            items.append({
                "title": f"Cardinals News: {title}",
                "description": title,
                "pub_date": pub_date,
                "guid": f"cardinals-web-{guid}",
                "link": link,
            })
        except Exception as e:
            print(f"[Cardinals Website] skipping malformed item: {e}")
            continue
        if len(items) >= limit:
            break

    print(f"[Cardinals Website] parsed {len(items)} articles")
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
        get_cardinals_games()
        + get_cardinals_news()
        + get_cardinals_website_news()
      
    )
    build_rss(items)


if __name__ == "__main__":
    main()
