"""Download N4EK flights from adsb.aero into flights.json.

First run backfills the last two years (or as far as the archive goes).
Later runs only fetch flights since the previous run, so run it once a day.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://adsb.aero/api/v1"
REGISTRATION = "N4EK"
OUT = Path(__file__).parent / "site" / "flights.json"
# Flights are ingested in daily batches, so re-read a few days of overlap.
OVERLAP = timedelta(days=3)


def request(path, body=None):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "User-Agent": f"{REGISTRATION.lower()}-flight-hours"},
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    now = datetime.now(timezone.utc)
    data = json.loads(OUT.read_text()) if OUT.exists() else {"flights": {}}

    archive_start = parse(request("/data-range")["first_date"] + "T00:00:00Z")
    two_years_ago = now.replace(year=now.year - 2)
    window_start = max(two_years_ago, archive_start)

    if "last_updated" in data:
        start_from = max(parse(data["last_updated"]) - OVERLAP, window_start)
    else:
        start_from = window_start

    body = {
        "match": {"registration_prefix": REGISTRATION},
        "include_path": False,
        "limit": 1000,
        "start_from": iso(start_from),
    }
    flights = data["flights"]
    before = len(flights)
    cursor = None
    while True:
        page = request("/query", {**body, "cursor": cursor} if cursor else body)
        for f in page["flights"]:
            # The API only matches by prefix, so N4EK would also match N4EKA etc.
            if f.get("registration") != REGISTRATION:
                continue
            flights[f["flight_id"]] = {k: v for k, v in f.items() if v is not None}
        print(f"read back to {page['window_from'][:10]}, {len(flights)} flights")
        cursor = page["cursor"]
        if not cursor:
            break

    data.update(
        registration=REGISTRATION,
        archive_start=iso(archive_start),
        window_start=iso(window_start),
        last_updated=iso(now),
        flights=flights,
    )
    OUT.write_text(json.dumps(data, indent=1))
    print(f"{len(flights) - before} new flights, {len(flights)} total -> {OUT.name}")


if __name__ == "__main__":
    main()
