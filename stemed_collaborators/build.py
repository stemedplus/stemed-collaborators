"""Find Collaborators: build the page from STEMEd+ Commons profiles.

    python -m stemed_collaborators --refresh [--force]   read Commons, update data/collaborators.json
    python -m stemed_collaborators --out output           write the page from the saved copy

The saved copy, data/collaborators.json, is not in the repository: the workflow keeps the last good copy in
the GitHub Actions cache. Without it the page still builds, with no people cards.

The page is one file, index.html, with the cards built in, so it also opens straight from a download.
"""
import argparse
import datetime as dt
import json
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import commons, directory

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ("stemedplus-commons-logo.png", "stemedplus-commons-logo-white.png", "stemedplus-theme.css",
          "manrope.woff", "manrope-OFL.txt")
MARK = "/*__DATA__*/null"


CONTACT = "https://stemedplus.org/contact-us/"


def load_organizations(path: Path = ROOT / "config" / "organizations.json") -> list:
    """Organization cards, checked: name, summary, and an https contact are required."""
    if not path.exists():
        return []
    out = []
    for i, o in enumerate(json.loads(path.read_text(encoding="utf-8")).get("organizations", [])):
        for key in ("name", "summary", "contact"):
            if not str(o.get(key, "")).strip():
                raise SystemExit(f"config/organizations.json, organization {i + 1}: {key} is required")
        for key in ("contact", "website"):
            if o.get(key) and not str(o[key]).startswith("https://"):
                raise SystemExit(f"config/organizations.json, {o['name']}: {key} must start with https://")
        added = str(o.get("added", "")).strip()
        if added and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", added):
            raise SystemExit(f"config/organizations.json, {o['name']}: added must be YYYY-MM-DD")
        logo = str(o.get("logo", "")).strip()
        if logo and not logo.startswith("https://") and not (ROOT / "site" / logo).exists():
            raise SystemExit(f"config/organizations.json, {o['name']}: logo {logo} is not in site/")
        tags, offers, needs = directory.split_interests([str(x).strip() for x in o.get("interests", []) if str(x).strip()])
        out.append({"name": o["name"].strip(), "lead": str(o.get("lead", "")).strip(), "summary": o["summary"].strip(),
                    "looking_for": str(o.get("looking_for", "")).strip(), "logo": logo,
                    "interests": tags, "offers": offers, "needs": needs,
                    "website": str(o.get("website", "")).strip(), "contact": o["contact"].strip(), "added": added})
    return out


def page_data(config: dict, data: dict) -> dict:
    required, opt_in, _ = directory.listing_rules(config)
    return {
        "updated": data.get("updated"),
        "counts": data.get("counts") or {},
        "preview": not required,  # true: everyone with interests is listed (the opt-in step is not shown)
        "opt_in_interest": opt_in,
        "edit_profile": commons.EDIT_PROFILE,
        "directory": commons.BASE + "/members/",
        "join_url": config.get("join_url", ""),
        "people": data.get("people") or [],
        "organizations": load_organizations(),
        "contact_url": CONTACT,
    }


PEOPLE_FIELDS = ("name", "username", "institution", "orcid", "photo", "profile", "interests", "offers", "needs")


def data_file(config: dict, payload: dict) -> dict:
    """collaborators.json: the same public card data the page shows, for other sites and tools."""
    site = config.get("site_url", "")
    return {
        "about": "STEMEd+ Find Collaborators: public card data from STEMEd+ Commons profiles, updated daily. "
                 "People are listed from their public profiles; organizations ask to be added.",
        "page": site,
        "updated": payload["updated"],
        "people": [{k: p.get(k) for k in PEOPLE_FIELDS} for p in payload["people"]],
        "organizations": payload["organizations"],
    }


def organizations_rss(config: dict, organizations: list) -> str:
    """feeds/organizations.xml: organization cards, newest first by their "added" date."""
    site = config.get("site_url", "")
    items = []
    for o in sorted(organizations, key=lambda o: o.get("added", ""), reverse=True):
        link = o.get("website") or o["contact"]
        parts = [o["summary"]]
        if o.get("looking_for"):
            parts.append("Looking for: " + o["looking_for"])
        if o.get("offers"):
            parts.append("We can offer: " + ", ".join(o["offers"]))
        if o.get("needs"):
            parts.append("We're looking for: " + ", ".join(o["needs"]))
        parts.append("Contact: " + o["contact"])
        date = ""
        if o.get("added"):
            day = dt.datetime.strptime(o["added"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            date = f"<pubDate>{format_datetime(day)}</pubDate>"
        items.append(f"<item><title>{escape(o['name'])}</title><link>{escape(link)}</link>"
                     f"<guid isPermaLink=\"false\">{escape(site + '#org-' + re.sub(r'[^a-z0-9]+', '-', o['name'].lower()).strip('-'))}</guid>"
                     f"{date}<description>{escape(' '.join(parts))}</description></item>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            "<title>STEMEd+ Find Collaborators: organizations</title>"
            f"<link>{escape(site)}</link>"
            f'<atom:link href="{escape(site)}feeds/organizations.xml" rel="self" type="application/rss+xml"/>'
            "<description>Organizations open to collaboration on STEMEd+ Commons, newest first.</description>"
            "<language>en</language>" + "".join(items) + "</channel></rss>\n")


def build(out: Path, config: dict = None, data: dict = None) -> dict:
    config = config or directory.load_config()
    data = data if data is not None else directory.load_data()
    payload = page_data(config, data)
    page = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    if MARK not in page:
        raise SystemExit("site/index.html has lost its data marker " + MARK)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page.replace(MARK, blob), encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(ROOT / "site" / name, out / name)
    (out / "collaborators.json").write_text(
        json.dumps(data_file(config, payload), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "feeds").mkdir(exist_ok=True)
    (out / "feeds" / "organizations.xml").write_text(organizations_rss(config, payload["organizations"]), encoding="utf-8")
    print(f"Wrote the page with {len(payload['people'])} people and {len(payload['organizations'])} organization card(s)"
          f"{'' if payload['preview'] else ' (opt-in required)'}.")
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--refresh", action="store_true", help="read Commons and update data/collaborators.json")
    ap.add_argument("--force", action="store_true", help="with --refresh: accept a large drop in cards")
    args = ap.parse_args(argv)
    if args.refresh:
        changed, message = directory.refresh(force=args.force)
        print(message)
        return 0
    build(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
