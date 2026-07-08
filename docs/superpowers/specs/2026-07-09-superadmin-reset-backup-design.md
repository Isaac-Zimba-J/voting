# Superadmin Role, Admin Creation, and Reset/Backup — Design

Date: 2026-07-09

## Context

Today there are only two account tiers (`CustomUser.user_type`: `1=Admin`,
`2=Voter`). The single Admin account per deployed instance is seeded once,
at container startup, via `DJANGO_SUPERUSER_EMAIL`/`DJANGO_SUPERUSER_PASSWORD`
env vars and `script/create_superuser.py` — there is no way to create a
second Admin account short of editing `.env` and restarting the container,
and there is no way to clear out an election's data (voters, candidates,
positions, votes) short of connecting to the database directly.

The user wants: a top-level "Superadmin" tier (the existing seeded account
on both live instances, cbuvoting1 and cbuvoting2, should become this
automatically) that can create ordinary Admin accounts through the app
itself, and can reset an instance's election data back to empty — with a
downloadable backup of that data available first, in case it's needed
later.

## Goals

- A `Superadmin` tier with everywhere an `Admin` can go, plus two
  additional pages only it can reach.
- Existing seeded accounts on both live instances (cbuvoting1, cbuvoting2)
  automatically become Superadmin on the next deploy, with zero manual
  steps — they're the only `is_superuser=True` account on each instance
  today.
- A **Create Admin** page: superadmin fills in email/first name/last
  name/password, submits, one new `user_type=1` account is created.
- A **Reset & Backup** page:
  - **Download Backup** — a JSON file containing all `Position`,
    `Candidate`, `Votes`, and `Voter` rows (plus each voter's linked
    `CustomUser`, restricted to `user_type=2` — admin/superadmin
    credentials are never included in a backup).
  - **Reset Data** — deletes all of the above (including the `user_type=2`
    `CustomUser` accounts linked to deleted voters, so no orphaned
    accounts are left behind), gated behind typing a confirmation phrase.
    Admin and Superadmin accounts are never touched by reset.

## Non-goals

- Not building a bootstrap/template mechanism for spinning up brand-new
  association instances from a dump — the existing per-instance Docker
  deployment process (from `DEPLOYMENT.md`) already handles that; this
  backup is for disaster-recovery/safety on an *existing* instance only.
- Not adding a restore-from-backup feature in this round — the backup is
  a downloadable safety net; restoring it back in is a manual/future
  concern, not built here.
- Not forcing "download a backup" before allowing a reset — the page
  recommends it, doesn't require it.
- Not changing bulk voter import (already shipped) or self-registration —
  this only touches account tiers, admin creation, and data reset/backup.

## Data model

In `account/models.py`, add a new choice to `CustomUser.USER_TYPE`:

```python
USER_TYPE = ((0, "Superadmin"), (1, "Admin"), (2, "Voter"))
```

(`user_type` itself is unchanged — still a `CharField(default=2,
choices=USER_TYPE, max_length=1)`.)

A migration adds this choice and includes a data migration step that sets
`user_type='0'` for every existing `CustomUser` where `is_superuser=True`
— on both live instances, that's exactly the one seeded account each,
which is what makes them Superadmin automatically after this deploys.

`script/create_superuser.py` (the container-startup seeding script) sets
`user_type=0` instead of `user_type=1` for newly-seeded accounts, so any
*future* fresh instance's first account is a Superadmin from the start,
consistent with the auto-promoted existing ones.

## Access control changes

`account/middleware.py`'s `AccountCheckMiddleWare` currently redirects any
`user_type != '1'` user away from `administrator.views`. This broadens to
allow `user_type in ('0', '1')` — Superadmin gets identical access to
every existing admin page, unchanged behavior for Admin.

`account/views.py:account_login`'s post-login redirect (`if
user.user_type == '1': redirect to adminDashboard`) broadens the same way
— Superadmin lands on the same admin dashboard Admin does. No new
dashboard; Superadmin's two extra pages just aren't visible/reachable to
a plain Admin (both nav visibility and a view-level check redirecting
non-superadmins who hit the URL directly — visibility alone isn't a
security boundary).

## Create Admin page

New view + template, following the existing `administrator/admin/*.html`
pattern:

- **Route:** `administrator/urls.py` — `path('admin/create',
  views.create_admin, name='createAdmin')`.
- **View:** superadmin-only (redirect with an error message if
  `request.user.user_type != '0'`). A plain form (email, first name, last
  name, password) that on POST creates one `CustomUser` via
  `CustomUser.objects.create_user(email=..., password=..., first_name=...,
  last_name=..., user_type=1)`.
- **Template:** `administrator/templates/admin/create_admin.html`, a
  simple form page in the same visual style as the existing voters page,
  linked from the sidebar only when `request.user.user_type == '0'`.

## Reset & Backup page

- **Route:** `administrator/urls.py` — `path('admin/reset-backup',
  views.reset_backup, name='resetBackup')`, superadmin-only (same gating
  pattern as Create Admin).
- **Download Backup** (a GET-triggered file download, or a POST button —
  implementation detail for the plan): serializes, via
  `django.core.serializers.serialize('json', queryset)`, the combined
  contents of `Position.objects.all()`, `Candidate.objects.all()`,
  `Votes.objects.all()`, `Voter.objects.all()`, and
  `CustomUser.objects.filter(user_type=2)` into one JSON file, returned as
  an `HttpResponse` with `Content-Disposition: attachment` and a
  timestamped filename (e.g. `voting-backup-2026-07-09-143000.json`).
- **Reset Data**: a form requiring the admin to type a literal
  confirmation phrase (e.g. `RESET`) into a text field before the POST is
  accepted (checked server-side, not just disabled via JS — a client-only
  check is not a real gate). On confirmed submission, in one
  `transaction.atomic()` block: delete all `Votes`, then all `Candidate`,
  then all `Position`, then for each `Voter` delete its linked
  `CustomUser` (which cascades to delete the `Voter` row too, since
  `Voter.admin` is `on_delete=CASCADE` — deleting the `CustomUser` side is
  what actually removes both cleanly in one step, rather than deleting
  `Voter` first and orphaning its `CustomUser`). Admin/Superadmin accounts
  are never queried or touched by this path (only `Voter`-linked accounts,
  which by construction are always `user_type=2`).

## Testing / verification plan

Consistent with this project's existing conventions (no formal test
suite; verification via real Django shell/test-Client runs against
throwaway databases, with pasted evidence):

- Confirm the migration promotes an `is_superuser=True` account to
  `user_type='0'` and leaves other accounts untouched.
- Confirm a Superadmin can reach every existing admin page (regression)
  and both new pages; confirm a plain Admin is redirected away from both
  new pages/URLs even when visiting them directly.
- Create Admin: submit the form, confirm the new account has
  `user_type=1` and can log in and reach admin pages but not the two
  superadmin-only ones.
- Backup: seed some Positions/Candidates/Votes/Voters, download the
  backup, confirm the JSON contains exactly those records and does not
  contain the Admin/Superadmin `CustomUser` rows or their password
  hashes.
- Reset: seed the same data, submit reset with the wrong confirmation
  text (expect nothing deleted), then with the correct text (expect
  Positions/Candidates/Votes/Voters and their linked `user_type=2`
  accounts all gone, Admin/Superadmin accounts still present and still
  able to log in).
