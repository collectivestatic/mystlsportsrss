#!/usr/bin/env python3
"""
Generates an RSS feed combining the St. Louis Cardinals and
St. Louis City SC schedules.

Data sources (both free, no API key required):
  - Cardinals: MLB Stats API (statsapi.mlb.com)
  - City SC:   ESPN's public soccer schedule endpoint

Run this on a timer (see .github/workflows/update-feed.yml) to keep
feed.xml up to date automatically.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import requests

# ---- Config -----------------------------------------------------------

CARDINALS_TEAM_ID = 138       # St. Louis Cardinals (MLB)
CITY_SC_TEAM_ID = 21812       # St. Louis City SC (ESPN team id, MLS)

DAYS_BEHIND = 3               # include recently completed games
DAYS_AHEAD = 14               # include upcoming games

FEED_TITLE = "STL Sports Schedule — Cardinals & City SC"
# IMPORTANT: update this to match your actual GitHub Pages URL once deployed,
# e.g. https://yourusername.github.io/stl-sports-feed/feed.xml
FEED_LINK = "https://collectivestatic.github.io/mystlsportsrss/feed.xml"
FEED_DESCRIPTION = "Auto-updated schedule and results for the St. Louis Cardinals and St. Louis City SC"

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


# ---- Cardinals (MLB Stats API) ------------------------------------------

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


# ---- St. Louis City SC (ESPN) --------------------------------------------

def get_city_sc_games():
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/teams"
        f"/21812/schedule"
    )

    items = []
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[City SC] fetch failed: {e}")
        return items

    for event in data.get("events", []):
        try:
          competitors = event["competitions"][0]["competitors"]
city_sc = next(
    c for c in competitors
    if str(c.get("team", {}).get("id")) == str(CITY_SC_TEAM_ID)
)
opponent = next(c for c in competitors if c is not city_sc)

is_home = city_sc.get("homeAway") == "home"
venue = "Home" if is_home else "Away"
status_desc = event.get("status", {}).get("type", {}).get("description", "Scheduled")
completed = event.get("status", {}).get("type", {}).get("completed", False)

game_dt = _parse_iso(event["date"], ["%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"])

opponent_id = str(opponent.get("team", {}).get("id"))
opponent_name = opponent["team"]["displayName"]
# ESPN fills TBD bracket slots with our own team's info instead of "TBD"
if opponent_id == str(CITY_SC_TEAM_ID):
    opponent_name = "TBD"

title = f"City SC ({venue}) vs {opponent_name} — {status_desc}"

            if completed:
                city_score = city_sc.get("score", "?")
                opp_score = opponent.get("score", "?")
                description += f" Final score: City SC {city_score} – {opp_score} {opponent_name}."

            items.append({
                "title": title,
                "description": description,
                "pub_date": game_dt,
                "guid": f"citysc-{event.get('id')}",
                "link": FEED_LINK,
            })
        except (KeyError, ValueError, StopIteration) as e:
            print(f"[City SC] skipping malformed event: {e}")
            continue

    print(f"[City SC] parsed {len(items)} games")
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
    items = get_cardinals_games() + get_city_sc_games()
    build_rss(items)


if __name__ == "__main__":
    main()
