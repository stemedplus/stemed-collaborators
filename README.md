# Find Collaborators (STEMEd+ Commons)

Find people to work with across STEM+ teaching and STEM+ education research, by the interests and skills on their
**STEMEd+ Commons profiles**. Part of [STEMEd+ Commons](https://stemedplus.org/).

There is no separate sign-up. People are listed by filling in their own Commons profile, and the page
updates itself every day.

## How it works

1. **Who's a member.** Every day, GitHub reads the STEMEd+ Commons
   [Profiles API members list](https://stemedplus.profile.hcommons.org/api/v1/members/), which gives every
   member's public name, institution, ORCID iD, and **academic interests**. Nothing is scraped from web pages.
2. **Photos.** The list has no photos, so it also reads each member's one-member API record
   (`/api/v1/members/<username>/`) for the photo.
3. **Who gets a card.** Every STEMEd+ member. Cards are sorted with people who have added academic interests
   first; a card without interests shows "Is this you? Add your interests", linking to **Edit profile**.
4. **Search.** The page searches interests, skills, names, and institutions. Clicking an interest shows
   everyone else with it, and the most common interests are listed as one-click searches.
5. **Adding interests.** The page invites people to sign in, open **Edit profile**, and add academic
   interests, including their skills and methods. They appear on their card at the next daily update.
6. **Contact.** Each card links to the person's profile, where they list the ways to reach them. (Knowledge
   Commons no longer has direct messages.)

Only public profile fields are used. Nothing is collected from people directly.

## Organizations (config/organizations.json)

Organizations open to collaboration get their own cards, shown first and marked "Organization": a summary,
what they are looking for, searchable interest tags, a "Contact to collaborate" link, and their website.
Organizations ask to be added through the [STEMEd+ contact page](https://stemedplus.org/contact-us/), which the
page links to; a maintainer then adds an entry. Required: `name`, `summary`, `contact` (https). A `logo` is a
file in `site/` or an https address. The page has an Everyone / People / Organizations switch.

## Who is listed (config/site.json)

Everyone in the STEMEd+ members list gets a card, with or without academic interests. Cards show
only public profile fields; people get in touch through the contact links on each profile. To come off the page, a
member asks and a maintainer adds their username to `listing.exclude`.

`listing.opt_in_required` (default `false`) can list only members whose interests include
`listing.opt_in_interest` ("open to collaboration"); the page then asks people to add it.

## Publishing

`.github/workflows/update.yml` runs daily, on every push to `main`, and from the Actions tab. It refreshes the
cards in `data/collaborators.json`, builds the page, and publishes it to GitHub Pages while
`publish` in `config/site.json` is `true`. The workflow only reads the repository (`contents: read`); it never
commits. Turn on once: **Settings → Pages → Source: GitHub Actions**. On a free GitHub
account, Pages needs the repository to be public.

## Where the cards are kept

The cards hold copies of people's public profile details, so they are **not kept in the repository**:
`data/collaborators.json` is in `.gitignore`, and someone who leaves or edits their profile drops out of the
next build without staying in the Git history. The last good copy lives in the **GitHub Actions cache**
instead. Each run restores the newest entry whose key starts with `collaborators-data-`, refreshes it from
Commons, and saves the result as `collaborators-data-<run id>`. Older entries go unused and GitHub removes
them after 7 days. They can be seen and deleted under **Actions → Caches**.

If the cache is empty (the first run, or after the entries are deleted), the run starts from nothing and
builds the cards from the API; the page still builds if Commons is down, just without people cards.

## When Commons doesn't answer

Knowledge Commons is still changing its profile system. The members list pages 20 at a time with a "next"
link and no total; the build follows it to the end (switching the link from `http://` to `https://`, as the
API writes it with `http://`). If any page of the list can't be read, or the number of cards falls by more
than half, the last good copy is kept and the run log says why. If a member's own record doesn't answer,
their card keeps the photo from the last good copy. If a big drop is real, run
`python -m stemed_collaborators --refresh --force` once.

## Files

- `stemed_collaborators/commons.py`: reads the Profiles API (the members list, and one member for a photo).
- `stemed_collaborators/directory.py`: decides who gets a card and keeps the last good copy.
- `stemed_collaborators/build.py`: builds `index.html` with the cards built in.
- `site/index.html`: the page (search, cards, invitation). The green band and footer come from
  [stemedplus-theme](https://github.com/stemedplus/stemedplus-theme); don't edit them here.
- `data/collaborators.json`: the saved cards, made by `--refresh`. Not committed; the workflow keeps it in
  the Actions cache.
- `tests/`: `python -m unittest discover -s tests -t .`
