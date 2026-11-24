"""Read STEMEd+ Commons members and their public profiles through the Profiles API.

Two addresses of the STEMEd+ Commons Profiles API are used:

    https://stemedplus.profile.hcommons.org/api/v1/members/              every STEMEd+ member (JSON, 20 a page)
    https://stemedplus.profile.hcommons.org/api/v1/members/<u>/          one member's public profile (JSON)

The members list gives username, name, institution, ORCID iD and academic interests for every member. It pages
with a cursor: each page has "next" (the following page, or null) and no total. The list has no photo, so the
one-member address is read only for members who get a card, for their photo. Knowledge Commons is still
changing its profile system, so the build keeps the last good copy when the API stops answering (see
directory.py).
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterator, List, Optional, Tuple

BASE = "https://stemedplus.profile.hcommons.org"
MEMBERS = BASE + "/api/v1/members/"
API = BASE + "/api/v1/members/{username}/"
PROFILE = BASE + "/members/{username}/"
EDIT_PROFILE = BASE + "/edit-profile/"

# Commons usernames are mostly letters, digits, dots, dashes, and underscores, but some hold other
# characters (for example @ or +), so anything without a slash or a space is accepted and quoted in URLs.
USERNAME = re.compile(r"^[^/\s?#]{1,100}$")

OK, MISSING, UNAVAILABLE = "ok", "missing", "unavailable"
USER_AGENT = "stemed-collaborators (https://github.com/stemedplus/stemed-collaborators)"


def profile_url(username: str) -> str:
    return PROFILE.format(username=urllib.parse.quote(username, safe=""))


def http_get(url: str, accept: str = "application/json", timeout: float = 30) -> Tuple[int, str]:
    """(status, body). Status 0 means no answer at all."""
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError):
        return 0, ""


def next_page(page: dict, current_url: str) -> Optional[str]:
    """The list's "next" address, kept on https (the API writes it as http://)."""
    nxt = page.get("next")
    if not nxt or not isinstance(nxt, str):
        return None
    nxt = urllib.parse.urljoin(current_url, nxt)
    return "https://" + nxt[len("http://"):] if nxt.startswith("http://") else nxt


def list_members(get: Callable = http_get, max_pages: int = 2000, pause: float = 0.2, tries: int = 3) -> List[dict]:
    """Every STEMEd+ member from the members list, in API order, one record per username.

    Raises RuntimeError if any page can't be read, so a partial list never replaces the last good copy."""
    members, seen_names, seen_urls, url = [], set(), set(), MEMBERS
    while url:
        if url in seen_urls or len(seen_urls) >= max_pages:
            raise RuntimeError(f"members list stopped after {len(seen_urls)} pages (its next link repeats or never ends)")
        seen_urls.add(url)
        for attempt in range(tries):
            status, body = get(url)
            if status == 200:
                break
            time.sleep(pause * 10 * (attempt + 1))
        if status != 200:
            raise RuntimeError(f"members list answered {status or 'nothing'} at {url}")
        try:
            page = json.loads(body)
        except ValueError:
            raise RuntimeError(f"members list sent something that is not JSON at {url}") from None
        if not isinstance(page, dict) or not isinstance(page.get("results"), list):
            raise RuntimeError(f"members list page has no results at {url} (the API may have changed)")
        for record in page["results"]:
            name = str(record.get("username") or "") if isinstance(record, dict) else ""
            if USERNAME.match(name) and name.lower() not in seen_names:
                seen_names.add(name.lower())
                members.append(record)
        url = next_page(page, url)
        if url and pause:
            time.sleep(pause)
    if not members:
        raise RuntimeError("members list had no members")
    return members


def fetch(username: str, get: Callable = http_get) -> Tuple[str, Optional[dict]]:
    """("ok", data), ("missing", None) when Commons has no such member, or ("unavailable", None)."""
    if not username or not USERNAME.match(username):
        return MISSING, None
    status, body = get(API.format(username=urllib.parse.quote(username, safe="")))
    if status == 404:
        return MISSING, None
    if status != 200:
        return UNAVAILABLE, None
    try:
        data = json.loads(body)
    except ValueError:
        return UNAVAILABLE, None
    if not isinstance(data, dict) or str(data.get("username", "")).lower() != username.lower():
        return UNAVAILABLE, None
    return OK, data


def interests(data: dict) -> List[str]:
    """Academic interests as plain text, in profile order, without duplicates."""
    out = []
    for item in data.get("academic_interests") or []:
        text = item.get("text") if isinstance(item, dict) else item
        text = re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()
        if text and text.lower() not in (x.lower() for x in out):
            out.append(text)
    return out


def iter_profiles(usernames: List[str], get: Callable = http_get, workers: int = 6) -> Iterator[Tuple[str, str, Optional[dict]]]:
    """(username, status, data) for each username, read a few at a time."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, (status, data) in zip(usernames, pool.map(lambda u: fetch(u, get), usernames)):
            yield name, status, data
