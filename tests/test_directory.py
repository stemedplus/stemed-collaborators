import json
import tempfile
import unittest
from pathlib import Path

from stemed_collaborators import build, commons, directory

PROFILES = {
    "ana": {"username": "ana", "name": "Ana  Ruiz", "institutional_affiliation": "State U", "orcid": "0000-0001-2345-678X",
            "avatar": "https://hcommons.org/avatars/ana.jpg",
            "academic_interests": [{"id": 1, "text": "Science identity"}, {"id": 2, "text": "Open to collaboration"},
                                   {"id": 3, "text": "qualitative interviews"}]},
    "ben.k": {"username": "ben.k", "name": "Ben K", "academic_interests": [{"id": 4, "text": "psychometrics"}]},
    "cy": {"username": "cy", "name": "Cy", "academic_interests": []},
    "dee": {"username": "dee", "name": "Dee", "academic_interests": [{"id": 5, "text": "open to collaboration"}]},
    "eve@example.org": {"username": "eve@example.org", "name": "Eve", "academic_interests": []},
}


def listed(name):
    """A members-list record: the profile without its photo, as the list API returns it."""
    record = {k: v for k, v in PROFILES[name].items() if k != "avatar"}
    record["url"] = "http://stemedplus.profile.hcommons.org/api/v1/members/" + name + "/"
    return record


NEXT = "http://stemedplus.profile.hcommons.org/api/v1/members/?cursor=cD01OTA1MA%3D%3D"
LIST1 = {"next": NEXT, "previous": None, "results": [listed("ana"), listed("ben.k"), listed("cy")]}
LIST2 = {"next": None, "previous": commons.MEMBERS, "results": [listed("eve@example.org"), listed("dee"), listed("ana")]}


def fake_get(url, accept="application/json", timeout=20):
    if url == commons.MEMBERS:
        return 200, json.dumps(LIST1)
    if url == "https://stemedplus.profile.hcommons.org/api/v1/members/?cursor=cD01OTA1MA%3D%3D":
        return 200, json.dumps(LIST2)
    if url.startswith("http://"):
        raise AssertionError("asked for an http:// address: " + url)
    name = commons.urllib.parse.unquote(url.rstrip("/").split("/")[-1])
    return (200, json.dumps(PROFILES[name])) if name in PROFILES else (404, "")


def read(names):
    return commons.iter_profiles(names, get=fake_get, workers=2)


def members(*names):
    return [listed(n) for n in names]


def config(required=False, exclude=()):
    return {
            "listing": {"opt_in_required": required, "opt_in_interest": "open to collaboration", "exclude": list(exclude)}}


class MembersList(unittest.TestCase):
    def test_reads_every_page_on_https_once_per_member(self):
        found = commons.list_members(get=fake_get, pause=0)
        self.assertEqual([m["username"] for m in found], ["ana", "ben.k", "cy", "eve@example.org", "dee"])

    def test_unusual_usernames_are_quoted(self):
        self.assertEqual(commons.profile_url("eve@example.org"),
                         "https://stemedplus.profile.hcommons.org/members/eve%40example.org/")

    def test_a_failed_page_is_an_error_not_a_short_list(self):
        def get(url, accept=None):
            return (200, json.dumps(LIST1)) if url == commons.MEMBERS else (503, "")
        with self.assertRaises(RuntimeError):
            commons.list_members(get=get, pause=0)

    def test_repeating_next_link_is_an_error(self):
        loop = {"next": commons.MEMBERS, "results": [listed("ana")]}
        with self.assertRaises(RuntimeError):
            commons.list_members(get=lambda u, accept=None: (200, json.dumps(loop)), pause=0)

    def test_empty_or_changed_list_is_an_error(self):
        for body in ({"next": None, "results": []}, {"detail": "Authentication credentials were not provided."}):
            with self.assertRaises(RuntimeError):
                commons.list_members(get=lambda u, accept=None, b=body: (200, json.dumps(b)), pause=0)


class Cards(unittest.TestCase):
    def names(self, cfg):
        cards, counts = directory.collect(members("ana", "ben.k", "cy", "dee"), cfg, read)
        return [c["username"] for c in cards], cards, counts

    def test_everyone_gets_a_card_with_or_without_interests(self):
        names, cards, counts = self.names(config())
        self.assertEqual(names, ["ana", "ben.k", "cy", "dee"])
        self.assertEqual((counts["members"], counts["listed"], counts["no_interests"]), (4, 4, 2))
        by = {c["username"]: c for c in cards}
        self.assertEqual(by["cy"]["interests"], [])
        self.assertEqual(by["dee"]["interests"], [])       # only the opt-in interest, which is hidden
        ana = cards[0]
        self.assertEqual(ana["interests"], ["Science identity", "qualitative interviews"])   # opt-in tag hidden
        self.assertEqual(ana["name"], "Ana Ruiz")
        self.assertTrue(ana["opted_in"])
        self.assertEqual(ana["orcid"], "0000-0001-2345-678X")
        self.assertEqual(ana["photo"], "https://hcommons.org/avatars/ana.jpg")   # from her own profile

    def test_photo_kept_from_last_copy_when_profile_does_not_answer(self):
        down = lambda names: ((n, commons.UNAVAILABLE, None) for n in names)
        cards, counts = directory.collect(members("ana", "ben.k"), config(), down,
                                          {"ana": "https://hcommons.org/avatars/ana-old.jpg"})
        self.assertEqual([c["photo"] for c in cards], ["https://hcommons.org/avatars/ana-old.jpg", ""])
        self.assertEqual(counts["photo_not_read"], 2)

    def test_opt_in_required(self):
        names, _, _ = self.names(config(required=True))
        self.assertEqual(names, ["ana", "dee"])

    def test_exclude(self):
        names, _, _ = self.names(config(exclude=["ANA"]))
        self.assertEqual(names, ["ben.k", "cy", "dee"])


class Refresh(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "data.json"

    def run_refresh(self, **kw):
        return directory.refresh(self.tmp, config(), list_members=lambda: members("ana", "ben.k", "cy", "dee"), read=read, **kw)

    def test_writes_then_no_change(self):
        changed, msg = self.run_refresh()
        self.assertTrue(changed, msg)
        self.assertEqual(len(json.loads(self.tmp.read_text())["people"]), 4)
        changed, msg = self.run_refresh()
        self.assertFalse(changed)
        self.assertIn("No change", msg)

    def test_keeps_last_copy_when_members_list_fails(self):
        self.run_refresh()
        def broken():
            raise RuntimeError("members list answered 503")
        changed, msg = directory.refresh(self.tmp, config(), list_members=broken, read=read)
        self.assertFalse(changed)
        self.assertIn("Kept the last good copy", msg)

    def test_keeps_last_copy_when_cards_drop_by_half(self):
        self.run_refresh()
        changed, msg = directory.refresh(self.tmp, config(), list_members=lambda: members("cy"), read=read)
        self.assertFalse(changed)
        self.assertEqual(len(json.loads(self.tmp.read_text())["people"]), 4)

    def test_empty_cache_first_run_writes_cards(self):
        # The workflow keeps the last good copy in the Actions cache; on a first run there is none.
        self.assertFalse(self.tmp.exists())
        changed, msg = self.run_refresh()
        self.assertTrue(changed, msg)
        self.assertEqual(len(json.loads(self.tmp.read_text())["people"]), 4)

    def test_empty_cache_and_commons_down_writes_nothing(self):
        def broken():
            raise RuntimeError("members list answered 503")
        changed, _ = directory.refresh(self.tmp, config(), list_members=broken, read=read)
        self.assertFalse(changed)
        self.assertFalse(self.tmp.exists())


class Page(unittest.TestCase):
    def test_build_without_saved_cards(self):
        # Empty Actions cache and Commons down: the page still builds, with no people cards.
        missing = Path(tempfile.mkdtemp()) / "data" / "collaborators.json"
        out = Path(tempfile.mkdtemp())
        payload = build.build(out, config(), directory.load_data(missing))
        self.assertEqual(payload["people"], [])
        self.assertNotIn(build.MARK, (out / "index.html").read_text())

    def test_build_puts_cards_in_the_page(self):
        cards, counts = directory.collect(members("ana", "ben.k"), config(), read)
        out = Path(tempfile.mkdtemp())
        payload = build.build(out, config(), {"updated": "2026-11-16T00:00:00Z", "counts": counts, "people": cards})
        html = (out / "index.html").read_text()
        self.assertNotIn(build.MARK, html)
        self.assertIn('"preview":true', html)
        self.assertIn("Science identity", html)
        self.assertIn("Add your interests", html)
        self.assertTrue(payload["preview"])
        self.assertTrue((out / "stemedplus-theme.css").exists())


if __name__ == "__main__":
    unittest.main()


class Organizations(unittest.TestCase):
    def test_stemedplus_card_is_valid(self):
        orgs = build.load_organizations()
        self.assertEqual(orgs[0]["name"], "STEMEd+ Commons")
        self.assertEqual(orgs[0]["contact"], "https://stemedplus.org/contact-us/")

    def test_required_fields(self):
        path = Path(tempfile.mkdtemp()) / "orgs.json"
        path.write_text(json.dumps({"organizations": [{"name": "X", "contact": "https://x.org/"}]}))
        with self.assertRaises(SystemExit):
            build.load_organizations(path)

    def test_contact_must_be_https(self):
        path = Path(tempfile.mkdtemp()) / "orgs.json"
        path.write_text(json.dumps({"organizations": [{"name": "X", "summary": "s", "contact": "mailto:a@b.org"}]}))
        with self.assertRaises(SystemExit):
            build.load_organizations(path)
