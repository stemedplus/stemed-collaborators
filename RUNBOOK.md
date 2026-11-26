# Runbook: Find Collaborators

This board uses the shared STEMEd+ pipeline. For how every board works and the common fixes, see the [stemedplus-theme runbook](https://github.com/stemedplus/stemedplus-theme/blob/main/RUNBOOK.md).

| | |
|---|---|
| **Site** | stemedplus.github.io/stemed-collaborators |
| **Repository** | stemedplus/stemed-collaborators |
| **Updates** | Daily at 10:23 UTC, on push, and by hand (`update.yml`) |
| **Sources** | Public STEMEd+ member directory and public profiles on Knowledge Commons; organizations in `config/organizations.json` |
| **Data** | Collaborator cards live in the Actions cache, never in Git |
| **Build** | `python -m stemed_collaborators --refresh`, then `--out output` |

**Someone wants off the page:** they remove their academic interests from their profile, or a maintainer adds their username to `listing.exclude` in `config/site.json`.

**Add an organization:** they ask through the contact form; add an entry to `config/organizations.json` (name, summary, https contact).

**Knowledge Commons doesn't answer:** the run keeps the last good cards from the cache. See the README section "When Commons doesn't answer."

**Preview vs. published:** `publish` in `config/site.json` controls whether the page is public.

_Written November 2026. Review with the yearly December review._
