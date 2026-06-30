# plex-bulk-invite

Bulk re-invite Plex users and restore their per-library access after a server
migration that detached or lost your shares.

If you've ever migrated/restored a Plex Media Server, watched the server
re-register on plex.tv under a new identity, and found that **every user in
Manage Library Access vanished** - this is for you. When the share/friend
records are gone at the plex.tv account level, you can't simply "re-share"; you
have to **re-invite** everyone. Doing that by hand for dozens of users is
miserable. This script automates it.

---

## What it does

- Reads your historical user list from an **old Tautulli database**, which
  stores each user's **email** and the **exact libraries** they had
  (`users.shared_libraries`).
- Maps the old library section IDs to the libraries that **still exist** on your
  current server, dropping any removed/renamed libraries automatically.
- Sends each user a friend invite via PlexAPI (`account.inviteFriend()`) with
  their original libraries pre-selected.
- Supports a **baseline** library set granted to everyone, plus **per-user
  restricted libraries** (e.g. a private library that should go to exactly one
  person).
- Ships with a **`REPORT_ONLY` dry-run mode** so you can verify every
  assignment before a single invite goes out.

Users who are still friends of your account get re-shared **instantly** (no
acceptance needed). Users whose friendship was also severed get a normal
pending invite to accept at app.plex.tv.

---

## Why Tautulli is the key

After this kind of share loss, your Plex server database only retains user
**names** in its `accounts` table - no emails. Re-inviting requires email
addresses. Tautulli, however, logs every user's `username`, `email`, and
`shared_libraries` in its `users` table. If you have an old `tautulli.db` from
when your shares were intact, it is the single best source for rebuilding your
share list with each person's original library access.

---

## Background

This script was written to recover from a real incident: a Windows -> Linux
Plex migration where the server re-registered under a new identity and detached
all Manage Library Access shares. Restoring the original
`ProcessedMachineIdentifier` and re-claiming did **not** reattach the shares -
plex.tv created a new registration record, and Plex support confirmed shares
cannot be re-linked server-side once the original record is gone. The only
remaining path was a scripted re-invite, driven by the old Tautulli database.

**Lessons learned (so you don't repeat them):**

- Don't remove the server from your plex.tv **Devices** list while
  troubleshooting share problems - it can permanently sever the original
  share/friend records.
- Plex's invite **emails are unreliable**. Tell users to accept at
  **app.plex.tv**, not to wait for an email.
- Library section IDs in the old Tautulli DB may not match the new server if you
  added/removed libraries. This script only grants IDs that exist on the live
  server, so mismatches are dropped safely.
- Watch history survives. It's keyed to each user's Plex **account ID** in your
  server database and reattaches when the user connects (verified: 10,000+
  history rows intact for a test account post-recovery).

---

## Tested environment

Developed and run successfully on:

| Component | Detail |
| --- | --- |
| Server | Dell PowerEdge R730xd |
| CPU | 2x Intel Xeon E5-2698 v3 |
| RAM | 128 GB |
| GPU | NVIDIA Quadro RTX 4000 |
| OS  | Ubuntu 25.10 |
| Plex Media Server | 1.42.2.10156-f737b826c (native systemd install) |
| Python | 3.x |
| PlexAPI | 4.18.1 |
| Tautulli DB schema | `users` table with `username`, `email`, `shared_libraries` |

It is not version-locked to the above; these are simply the versions it's
confirmed working on.

---

## Requirements

```bash
pip install plexapi
```

You also need:

- A copy of your **Tautulli database** (`tautulli.db`) from when your shares
  were intact.
- Your Plex **server URL** and an **admin (owner) X-Plex-Token**
  ([how to find your token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)).

---

## Configuration

Open `plex_bulk_reinvite.py` and edit the CONFIG block:

```python
PLEX_URL    = "http://YOUR_SERVER_IP:32400"
PLEX_TOKEN  = "YOUR_PLEX_ADMIN_TOKEN"
TAUTULLI_DB = "/path/to/tautulli.db"

# Libraries EVERY user gets, by section id. Empty = original libs only.
BASELINE_IDS = set()           # e.g. {2, 3, 7, 8}

# Also merge in each user's original libraries from Tautulli (recommended).
USE_ORIGINAL_LIBS = True

# Restricted libs: section_id -> {allowed usernames}. Granted ONLY to those
# users; stripped from everyone else even if their Tautulli record had it.
RESTRICTED = {}                # e.g. {19: {"alice"}, 22: {"bob"}}

# Usernames to skip entirely (lowercased).
SKIP_USERS = set()

# Safety: True = print only, send nothing.
REPORT_ONLY = True
```

### Finding your library section IDs

Run the script with `REPORT_ONLY = True`. It prints every live library with its
numeric section id and title, then prints exactly what each user **would**
receive - without sending anything. Use that output to fill in `BASELINE_IDS`
and `RESTRICTED`.

---

## Usage

**1. Dry run (default - sends nothing):**

```bash
python3 plex_bulk_reinvite.py
```

Review the output. Confirm:

- Every restricted library appears only for its allowlisted user(s).
- Everyone has the baseline libraries you expect.
- The user count matches.

**2. Go live:**

Set `REPORT_ONLY = False`, then run again:

```bash
python3 plex_bulk_reinvite.py
```

It sends invites with a short delay between each and prints a `SENT` / `SKIP` /
`FAIL` line per user, plus a summary.

**3. Re-running is safe.** If some invites fail (the plex.tv API occasionally
throws transient errors) or you need to run again, already-pending invites are
simply reported as failures ("already exists") - they aren't duplicated. Fix any
genuine failures and re-run.

---

## After running

- Users who were still friends are re-shared immediately and appear in **Manage
  Library Access** right away.
- Users who got new invites must **accept** at **app.plex.tv** (not via email -
  it's unreliable).
- Watch history reattaches as each user connects.

---

## Disclaimer

Use at your own risk. This script sends real invites to real people. **Always
review the `REPORT_ONLY` output before going live.** Keep a backup of your
Tautulli database and your Plex `Preferences.xml`.

---

## Author

Maintained by **SethsFlix** - admin@sethsflix.com

Contributions and issues welcome.
