# STL Sports RSS Feed

Auto-updating RSS feed for the St. Louis Cardinals and St. Louis City SC,
built from two free, no-key APIs (MLB Stats API + ESPN) and hosted for free
on GitHub Pages.

## Setup (one-time)

1. **Create a GitHub repo.**
   Make it **public** — public repos get unlimited free GitHub Actions
   minutes. (Go to github.com → New repository.)

2. **Add these files to the repo root**, keeping the folder structure:
   ```
   your-repo/
   ├── generate_feed.py
   ├── .github/
   │   └── workflows/
   │       └── update-feed.yml
   └── README.md
   ```
   Easiest way: unzip this project and push it directly.
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

3. **Enable GitHub Pages.**
   In the repo: Settings → Pages → Source: "Deploy from a branch" →
   Branch: `main`, folder: `/ (root)` → Save.

4. **Update the feed URL in the script.**
   Open `generate_feed.py` and change `FEED_LINK` to your real Pages URL:
   ```
   https://YOUR_USERNAME.github.io/YOUR_REPO/feed.xml
   ```
   Commit and push that change.

5. **Run the workflow once manually.**
   Go to the Actions tab → "Update STL Sports RSS Feed" → "Run workflow".
   This generates `feed.xml` and commits it. After that it also runs
   automatically every day on the schedule in `update-feed.yml`.

6. **Test it.**
   Visit `https://YOUR_USERNAME.github.io/YOUR_REPO/feed.xml` in a browser —
   you should see the XML. Paste that same URL into any RSS reader, or into
   a Shortcuts "Get Contents of URL" action, to consume it.

## Notes

- The cron schedule runs in UTC. `13:00 UTC` ≈ 8:00 AM Central during
  daylight saving (CDT); during standard time (CST) that becomes 7:00 AM,
  so nudge the cron by an hour twice a year if that matters to you.
- The ESPN endpoint is unofficial/undocumented — reliable in practice but
  not guaranteed by ESPN. If it ever breaks, check the Action's run logs
  (it prints a `[City SC] fetch failed` message) — that's your signal to
  swap in an alternative source like TheSportsDB.
- `DAYS_BEHIND` / `DAYS_AHEAD` in `generate_feed.py` control how much of
  the schedule shows up in the feed at once — adjust to taste.
