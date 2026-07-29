# Password Management for Admins and Voters — Design

Date: 2026-07-29

## Context

There is currently no way to change a password anywhere in the system.
Voters get a password only once, at CSV-import or manual-add time
(auto-derived from their NRC/SIN, or set by an admin) - if an admin needs
to fix a locked-out voter's credentials, the only path today is deleting
and recreating their account. Admins/Superadmins have no way to change
their own password at all short of editing the database directly.

This matters right now because we've spent this session's other fixes
chasing voter login failures (autocapitalize mangling SIN input, case
mismatches). Even with those fixed, an admin will eventually need to reset
an individual voter's password directly - and no admin should be stuck
with a password only reachable via `.env`/`create_superuser.py`.

## Goals

- An admin/superadmin can set a **new password for any voter**, from the
  existing Edit Voter modal.
- Any logged-in admin or superadmin can **change their own password**,
  from a new dedicated page.

## Non-goals

- Voter self-service password change - out of scope per this round's
  decision; voters' passwords are admin-managed only.
- "Forgot password" / email-based reset flows - not building an email
  delivery mechanism here.
- Password strength/complexity rules - consistent with the rest of this
  app (bulk-imported passwords are just digits from an NRC), no new
  validation is introduced beyond "not empty".

## Part 1: Admin resets a voter's password (Edit Voter modal)

The Edit Voter modal (`administrator/templates/admin/voters.html`) and its
view (`administrator/views.py:updateVoter`) currently have two pre-existing
bugs that this work touches directly and fixes as part of the same pass
(same file, same underlying legacy `CustomUserForm`/`VoterForm` pattern
already replaced once for the Add Voter modal earlier this session):

- The field labeled "SIN" is actually wired to `email`, with the
  `@gmail.com`-if-no-`@` hack applied - it never touches `Voter.sin`.
- There is no password field in the modal at all (the backing form would
  technically accept one, but nothing renders it).

**Fix:** rewrite `updateVoter` the same way `voters` (Add) was rewritten -
read `first_name`, `last_name`, `sin`, `phone`, `password` directly from
POST instead of the ModelForm pair:

- `first_name`, `last_name`, `sin` - required.
- SIN uniqueness checked against *other* voters:
  `Voter.objects.filter(sin=sin).exclude(id=voter.id).exists()`.
- `phone` - optional, same as Add (empty string normalized to `None`).
- `password` - **optional**. Blank = keep the current password unchanged.
  Non-blank = call `user.set_password(new_password)` and save
  immediately - no auto-derivation from SIN here (unlike Add/import),
  since the admin is explicitly and deliberately choosing this value.
- Errors (missing required fields, duplicate SIN, duplicate phone) shown
  via `messages.error`, same pattern as Add - no bare `except:`, no silent
  failures.
- Template: the existing "SIN"-labeled input's `name` changes from
  `email` to `sin`; add one new optional Password input with a "leave
  blank to keep current password" placeholder, matching the Add modal's
  password-field style. The JS `getRow()` function (which
  fetches current values via `viewVoter`/`view_voter_by_id`) needs its
  `SIN` field wired to `voter.sin` instead of `voter.admin.email` to
  actually show the voter's SIN when the modal opens.

## Part 2: Admin/Superadmin changes their own password

New page, following the existing `administrator/admin/*.html` +
sidebar-link pattern (same shape as Create Admin / Reset & Backup, but
visible to *both* Admin and Superadmin, not superadmin-only):

- **Route:** `administrator/urls.py` -
  `path('settings/change-password', views.change_password,
  name='changePassword')`.
- **View:** available to any authenticated admin/superadmin (already
  enforced by existing middleware - any `administrator.views` view is
  off-limits to voters). Form fields: current password, new password,
  confirm new password.
  - Verify `request.user.check_password(current_password)`; wrong
    current password -> error, nothing changes.
  - `new_password` must match `confirm_password` and be non-empty.
  - On success: `request.user.set_password(new_password)`,
    `request.user.save()`, then
    **`update_session_auth_hash(request, request.user)`** - without this,
    Django invalidates the current session's auth hash on password
    change and the admin gets silently logged out immediately after
    changing their own password, which would be a confusing regression
    to ship.
- **Template:** `administrator/templates/admin/change_password.html`, a
  simple form page in the same visual style as the other settings pages.
- **Sidebar:** one new link under the existing "SETTINGS" section
  (`sidebar.html`, alongside "Ballot Position" / "Election Title"),
  visible whenever `request.user.user_type == '0' or user_type == '1'` -
  i.e. the same condition already gating that whole section, not a new
  superadmin-only gate.

## Testing / verification plan

Consistent with this project's existing conventions (no formal test
suite; verification via real Django test-Client runs against a throwaway
SQLite database, with pasted evidence):

- Edit Voter: create a voter, edit via the (updated) endpoint with a
  blank password - confirm the old password still logs in. Edit again
  with a new password - confirm the old password no longer logs in and
  the new one does. Confirm editing SIN to a value already used by
  another voter is rejected with a clear message and nothing is changed.
- Change Password: log in as an admin, submit the wrong current password
  - confirm rejected, original password still works. Submit matching
  new/confirm with the correct current password - confirm the session
  survives (no forced logout) and the new password works on a fresh
  login attempt while the old one no longer does.
