#!/usr/bin/env python
"""Retract votes cast by voters whose SIN/password was compromised, so
they can revote.

Matches a "Lastname, Firstname" list (one per line) against CustomUser
records for user_type=2 voters. DRY RUN by default - nothing is deleted
unless --apply is passed. Names that don't match exactly one voter are
never guessed at; they're reported so an admin can resolve them by hand.
Before deleting anything, a JSON backup of the exact vote records being
removed is written to the current directory.

Usage (inside the container):
    python script/retract_votes.py script/compromised_voters.txt
    python script/retract_votes.py script/compromised_voters.txt --apply
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_voting.settings')
import django
django.setup()

from django.core import serializers
from django.db import transaction

from account.models import CustomUser
from voting.models import Voter, Votes


def normalize(s):
    return re.sub(r'\s+', ' ', s.strip()).casefold()


def main():
    if len(sys.argv) < 2:
        print("Usage: python script/retract_votes.py <names_file> [--apply]")
        sys.exit(1)
    names_file = sys.argv[1]
    apply_changes = '--apply' in sys.argv[2:]

    with open(names_file, encoding='utf-8') as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    index = {}
    for user in CustomUser.objects.filter(user_type=2):
        try:
            voter = user.voter
        except Voter.DoesNotExist:
            continue
        key = (normalize(user.first_name), normalize(user.last_name))
        index.setdefault(key, []).append((user, voter))

    matched = []
    not_found = []
    ambiguous = []

    for line in raw_lines:
        if ',' not in line:
            not_found.append(line + "  (no comma - can't parse as Lastname, Firstname)")
            continue
        last, first = line.split(',', 1)
        key = (normalize(first), normalize(last))
        candidates = index.get(key, [])
        if len(candidates) == 1:
            user, voter = candidates[0]
            matched.append((line, user, voter))
        elif len(candidates) == 0:
            not_found.append(line)
        else:
            ambiguous.append((line, candidates))

    print(f"Parsed {len(raw_lines)} names from {names_file}")
    print(f"Matched:    {len(matched)}")
    print(f"Not found:  {len(not_found)}")
    print(f"Ambiguous:  {len(ambiguous)}")
    print()

    if not_found:
        print("=== NOT FOUND (no changes made - check spelling/order manually in the admin UI) ===")
        for line in not_found:
            print(" -", line)
        print()

    if ambiguous:
        print("=== AMBIGUOUS (multiple voters share this name - no changes made, resolve manually) ===")
        for line, candidates in ambiguous:
            print(" -", line)
            for user, voter in candidates:
                print(f"     SIN {voter.sin}: {user.first_name} {user.last_name}")
        print()

    print("=== MATCHED (these will be affected) ===")
    total_votes = 0
    for line, user, voter in matched:
        vote_count = Votes.objects.filter(voter=voter).count()
        total_votes += vote_count
        print(f" - {line}  ->  SIN {voter.sin}, {vote_count} vote(s), currently voted={voter.voted}")
    print()
    print(f"Total vote records that would be deleted: {total_votes}")

    if not apply_changes:
        print()
        print("DRY RUN - nothing was changed. Re-run with --apply to actually delete "
              "these votes and reset voted=False so they can revote.")
        return

    if not matched:
        print("Nothing matched - nothing to apply.")
        return

    voter_ids = [voter.id for _, _, voter in matched]
    votes_to_delete = Votes.objects.filter(voter_id__in=voter_ids)

    backup_data = serializers.serialize('json', votes_to_delete)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
    backup_path = f"retracted-votes-backup-{timestamp}.json"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(backup_data)
    print(f"\nBackup of {votes_to_delete.count()} vote record(s) written to {backup_path}")

    with transaction.atomic():
        deleted_count, _ = votes_to_delete.delete()
        Voter.objects.filter(id__in=voter_ids).update(voted=False)

    print(f"Deleted {deleted_count} vote record(s). Reset voted=False for {len(voter_ids)} voter(s). "
          f"They can revote now.")


if __name__ == '__main__':
    main()
