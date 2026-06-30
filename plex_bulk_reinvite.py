#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plex_bulk_reinvite.py

Bulk re-invite Plex users (and restore their per-library access) after a server
migration that detached/lost your shares.

WHY THIS EXISTS
---------------
If you migrate or restore a Plex Media Server and the server re-registers with a
new identity on plex.tv, your existing library shares can detach. In the worst
case the friend relationships are gone too, and you must RE-INVITE every user
rather than just re-share. Doing that by hand for dozens of users is brutal.

This script reads your historical user list from an OLD TAUTULLI DATABASE
(which stores each user's email AND the exact libraries they had), then sends
each person a friend invite via PlexAPI with their original libraries
pre-selected. Users who are still friends get re-shared instantly; users who are
no longer friends get a normal pending invite to accept.

REQUIREMENTS
------------
  pip install plexapi          (tested with plexapi 4.18.1)
  A copy of your Tautulli database (tautulli.db) from when shares were intact.
  Your Plex server URL and an admin (owner) X-Plex-Token.

HOW TO GET YOUR TOKEN
---------------------
  https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/

HOW TO FIND YOUR LIBRARY SECTION IDs
------------------------------------
  Run with REPORT_ONLY = True first. It prints every live library with its
  numeric section id and title, then prints what each user WOULD get. Nothing is
  sent while REPORT_ONLY is True.

NOTES
-----
- Section IDs in the Tautulli DB are from the OLD server. They usually match the
  restored DB, but this script only grants IDs that EXIST on the live server, so
  any removed/renamed libraries are dropped automatically.
- Watch history is keyed to each user's Plex account ID on your server and is
  preserved; it reattaches when the user connects.
- Plex's invite emails are unreliable. The dependable acceptance path is for the
  user to log into app.plex.tv and accept the pending invite there.

USE AT YOUR OWN RISK. Review the REPORT_ONLY output carefully before going live.
"""

import sqlite3
import time
from plexapi.server import PlexServer

# ===========================================================================
# CONFIG -- EDIT THESE
# ===========================================================================

PLEX_URL    = "http://YOUR_SERVER_IP:32400"   # e.g. http://192.168.1.10:32400
PLEX_TOKEN  = "YOUR_PLEX_ADMIN_TOKEN"
TAUTULLI_DB = "/path/to/tautulli.db"

# Libraries EVERY user should get, by section id (see REPORT_ONLY output).
# Leave empty ({}) to grant only each user's original libraries instead.
BASELINE_IDS = set()           # e.g. {2, 3, 7, 8}

# If True, also merge in each user's ORIGINAL libraries from Tautulli
# (recommended -- restores what they actually had, on top of any baseline).
USE_ORIGINAL_LIBS = True

# Restricted libraries: section_id -> set of usernames allowed (lowercased).
# A restricted library is granted ONLY to the listed usernames, and is stripped
# from everyone else even if their Tautulli record had it.
# Example: {19: {"alice"}, 22: {"bob"}}
RESTRICTED = {}

# Usernames to skip entirely (lowercased).
SKIP_USERS = set()

# Invite feature toggles (Plex Pass features ignored if you don't have it).
ALLOW_SYNC    = True
ALLOW_CAMERA  = False
ALLOW_CHANNELS = False

# Safety: True = print only, send nothing. Set False to actually send invites.
REPORT_ONLY = True

# Seconds between invites (be kind to the plex.tv API).
SLEEP_BETWEEN = 2

# ===========================================================================
# (No edits needed below this line)
# ===========================================================================

RESTRICTED_IDS = set(RESTRICTED.keys())

print("Connecting to Plex...")
plex = PlexServer(PLEX_URL, PLEX_TOKEN)
account = plex.myPlexAccount()

# Live section map: id -> title
live_sections = {int(s.key): s.title for s in plex.library.sections()}
print(f"\nLive libraries on this server ({len(live_sections)}):")
for sid in sorted(live_sections):
    print(f"  {sid:>3} | {live_sections[sid]}")
print()

# Read users from Tautulli
conn = sqlite3.connect(TAUTULLI_DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT user_id, username, email, shared_libraries
    FROM users
    WHERE deleted_user = 0
      AND is_admin = 0
      AND email IS NOT NULL
      AND email != ''
    ORDER BY username
""").fetchall()
conn.close()
print(f"Users read from Tautulli: {len(rows)}\n")


def compute_library_ids(username, shared_libraries_str):
    uname = (username or "").strip().lower()
    original = set()
    if shared_libraries_str:
        for tok in shared_libraries_str.split(";"):
            tok = tok.strip()
            if tok.isdigit():
                original.add(int(tok))

    granted = set(BASELINE_IDS)
    if USE_ORIGINAL_LIBS:
        for sid in original:
            if sid in live_sections and sid not in RESTRICTED_IDS:
                granted.add(sid)

    for sid, allowed in RESTRICTED.items():
        if uname in allowed and sid in live_sections:
            granted.add(sid)

    return {sid for sid in granted if sid in live_sections}


sent, skipped, failed = [], [], []

for row in rows:
    username, email = row["username"], row["email"]
    uname_lc = (username or "").strip().lower()

    if uname_lc in SKIP_USERS:
        skipped.append((username, email, "skip list"))
        print(f"SKIP   {username:<22} {email:<40} (skip list)")
        continue

    lib_ids = compute_library_ids(username, row["shared_libraries"])
    lib_titles = [live_sections[s] for s in sorted(lib_ids)]

    if not lib_titles:
        skipped.append((username, email, "no valid libraries"))
        print(f"SKIP   {username:<22} {email:<40} (no valid libraries)")
        continue

    if REPORT_ONLY:
        print(f"WOULD  {username:<22} {email:<40}")
        print(f"        -> {', '.join(lib_titles)}")
        sent.append((username, email, lib_titles))
        continue

    try:
        account.inviteFriend(
            user=email, server=plex, sections=lib_titles,
            allowSync=ALLOW_SYNC, allowCameraUpload=ALLOW_CAMERA,
            allowChannels=ALLOW_CHANNELS,
        )
        print(f"SENT   {username:<22} {email:<40}")
        print(f"        -> {', '.join(lib_titles)}")
        sent.append((username, email, lib_titles))
    except Exception as e:
        print(f"FAIL   {username:<22} {email:<40}")
        print(f"        ERROR: {e}")
        failed.append((username, email, str(e)))

    time.sleep(SLEEP_BETWEEN)

print("\n" + "=" * 70)
print("REPORT ONLY (nothing sent)" if REPORT_ONLY else "LIVE RUN SUMMARY")
print("=" * 70)
print(f"  Would send / sent: {len(sent)}")
print(f"  Skipped:           {len(skipped)}")
print(f"  Failed:            {len(failed)}")
if failed:
    print("\nFailed (safe to re-run; already-pending invites just re-report):")
    for u, e, why in failed:
        print(f"  {u} ({e}) - {why}")
