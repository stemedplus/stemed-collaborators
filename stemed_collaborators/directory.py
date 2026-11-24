"""Turn STEMEd+ Commons profiles into the cards on the Find Collaborators page.

    python -m stemed_collaborators --refresh      read Commons and update data/collaborators.json (not in Git)

Who gets a card (config/site.json, "listing"):
  * The member is in the STEMEd+ members list of the Profiles API (which decides membership) and their profile has at
    least one academic interest besides the opt-in interest.
  * When "opt_in_required" is true, their academic interests must also include the opt-in interest
    (for example "open to collaboration"). While it is false (the default), everyone with interests counts as
    opted in, and the page says so.
  * Usernames in "exclude" never get a card (for anyone who asks to be left out).

Only public profile fields are kept: name, username, institution, ORCID iD, photo, and interests.

data/collaborators.json holds people's profile details, so it is never committed (it is in .gitignore). The
daily workflow keeps the last good copy in the GitHub Actions cache, not in the repository: it restores the
newest copy before a refresh and saves the result after. A refresh replaces it only when the whole members list
was read, so a Commons outage never empties the page. With no saved copy (an empty cache, or a fresh
checkout), the refresh starts from nothing.
"""
import datetime as dt
import json
import re
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from . import commons

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "collaborators.json"
CONFIG = ROOT / "config" / "site.json"

MIN_KEPT = 0.5          # a refresh may not drop below half of the cards in the last good copy
PHOTO = re.compile(r"^https://[^\s\"'<>]+$")


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def listing_rules(config: dict) -> Tuple[bool, str, set]:
    rules = config.get("listing") or {}
    return (bool(rules.get("opt_in_required")),
            str(rules.get("opt_in_interest") or "open to collaboration").strip(),
            {str(u).lower() for u in rules.get("exclude") or []})


def same(a: str, b: str) -> bool:
    return re.sub(r"[^a-z0-9]+", " ", a.lower()).strip() == re.sub(r"[^a-z0-9]+", " ", b.lower()).strip()


def why_not(username: str, data: dict, config: dict) -> Optional[str]:
    """Why a profile gets no card ("excluded", "no_interests", "not_opted_in"), or None.

    Membership comes from the STEMEd+ members list itself. The profile's own "memberships" flags are not used:
    they disagree with each other ("STEMED+" and "STEMEd+") and with the list."""
    required, opt_in, exclude = listing_rules(config)
    if username.lower() in exclude:
        return "excluded"
    all_interests = commons.interests(data)
    if not [i for i in all_interests if not same(i, opt_in)]:
        return "no_interests"
    if required and not any(same(i, opt_in) for i in all_interests):
        return "not_opted_in"
    return None


def to_card(username: str, data: dict, config: dict) -> Optional[dict]:
    """The card for one profile, or None when it should not be shown."""
    if why_not(username, data, config):
        return None
    _, opt_in, _ = listing_rules(config)
    all_interests = commons.interests(data)
    opted_in = any(same(i, opt_in) for i in all_interests)
    shown = [i for i in all_interests if not same(i, opt_in)]
    name = re.sub(r"\s+", " ", str(data.get("name") or "")).strip() or username
    photo = str(data.get("avatar") or "").strip()
    orcid = str(data.get("orcid") or "").strip()
    return {
        "username": username,
        "name": name,
        "institution": re.sub(r"\s+", " ", str(data.get("institutional_affiliation") or "")).strip(),
        "orcid": orcid if re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", orcid) else "",
        "photo": photo if PHOTO.match(photo) and "mystery" not in photo else "",
        "interests": shown,
        "opted_in": opted_in,
        "profile": commons.profile_url(username),
    }


def collect(members: Iterable[dict], config: dict, read: Callable = commons.iter_profiles,
            old_photos: Optional[dict] = None) -> Tuple[List[dict], dict]:
    """Cards from the members list. Each listed member's own profile is read for their photo only; when it
    doesn't answer, the photo from the last good copy (old_photos, username -> address) is kept."""
    records = list(members)
    old_photos = old_photos or {}
    counts = {"members": len(records)}
    listed = []
    for record in records:
        username = str(record["username"])
        reason = why_not(username, record, config)
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
        else:
            listed.append(record)
    by_name = {str(r["username"]): r for r in listed}
    cards, unanswered = [], 0
    for username, status, data in read(list(by_name)):
        record = dict(by_name[username])
        if status == commons.OK:
            record["avatar"] = data.get("avatar")
        else:
            unanswered += 1
            record["avatar"] = old_photos.get(username.lower(), "")
        cards.append(to_card(username, record, config))
    if unanswered:
        counts["photo_not_read"] = unanswered
    cards.sort(key=lambda c: (c["name"].lower(), c["username"]))
    counts["listed"] = len(cards)
    return cards, counts


def load_data(path: Path = DATA) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"updated": None, "counts": {}, "people": []}


def refresh(path: Path = DATA, config: Optional[dict] = None, list_members: Callable = commons.list_members,
            read: Callable = commons.iter_profiles, now: Optional[dt.datetime] = None,
            force: bool = False) -> Tuple[bool, str]:
    """Update the saved copy from the Profiles API. Returns (changed, message)."""
    config = config or load_config()
    old = load_data(path)
    try:
        members = list_members()
    except RuntimeError as exc:
        return False, f"Kept the last good copy: {exc}."
    old_photos = {p["username"].lower(): p.get("photo", "") for p in old["people"]}
    cards, counts = collect(members, config, read, old_photos)
    if old["people"] and not force and len(cards) < MIN_KEPT * len(old["people"]):
        return False, (f"Kept the last good copy: this read found {len(cards)} cards, under half of the "
                       f"{len(old['people'])} saved. Check Commons, then run again with --force if this is right.")
    now = now or dt.datetime.now(dt.timezone.utc)
    new = {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "counts": counts, "people": cards}
    if new["people"] == old["people"] and new["counts"] == old.get("counts"):
        return False, f"No change: {counts['listed']} of {counts['members']} members listed."
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    skipped = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in counts.items()
                        if k in ("no_interests", "not_opted_in", "excluded"))
    note = (f" {counts['photo_not_read']} profiles didn't answer, so their photos are from the last copy."
            if counts.get("photo_not_read") else "")
    return True, (f"Updated: {counts['listed']} of {counts['members']} members listed "
                  f"(not listed, {skipped or 'none'}).{note}")
