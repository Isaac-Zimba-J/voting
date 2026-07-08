# SIN-Based Bulk Voter Import — Design

Date: 2026-07-08

## Context

Voters currently self-register one at a time via `account/views.py:account_register`,
providing an email, password, and phone number. For real elections, the
association instead collects student data (SIN, name, NRC) via a Google
Form, exported as a CSV from the resulting Google Sheet. The admin wants to
bulk-create voter accounts from that CSV, with students logging in using
their SIN (Student Identification Number) rather than an email, and a
password auto-generated from their name and NRC rather than self-chosen.

Note: the existing login form's placeholder text already says "SIN", but
there is no real `sin` field in the schema today — that text has always
referred to the `email` field. This feature introduces an actual `sin`
field and makes the placeholder's promise true.

## Goals

- Add a real, unique `sin` field to voter accounts.
- Let voters log in with their SIN in the existing login form, while admin
  accounts keep logging in with email exactly as today — no change to the
  admin login path.
- An admin-only CSV upload page that bulk-creates voter accounts from a
  `SN, SIN, NAME, NRC` sheet, auto-generating each student's password from
  their name and NRC.
- Handle NRC values entered with or without slashes (or any other
  separator) uniformly.
- Skip bad rows with a reported reason rather than failing the whole
  import; re-uploading the same or an updated CSV is safe (already-imported
  SINs are skipped, not duplicated).

## Non-goals

- No forced password change on first login (explicit choice — can be added
  later if needed).
- No self-service "forgot password" flow for SIN-based accounts (the
  password is deterministically derived from data already on file, not
  something students choose or reset themselves in this iteration).
- Not changing the self-registration flow (`account_register`) — it
  continues to exist alongside bulk import as a separate path.
- Not enforcing NRC format validation beyond "at least 4 digits present
  after stripping non-digit characters" — malformed-but-numeric NRCs are
  accepted as-is.

## Data model

Add to `voting/models.py`'s `Voter` model:

```python
sin = models.CharField(max_length=20, unique=True, null=True, blank=True)
```

Nullable because self-registered voters (via `account_register`) won't
have one. A migration adds this column.

`CustomUser.email` (`account/models.py`) stays `unique`/required as-is —
unchanged for admins. For bulk-imported students, the import generates a
placeholder value (`<sin>@students.local`) to satisfy that constraint; it
is never shown to the student or used for login.

## Login flow

`account/email_backend.py`'s `EmailBackend.authenticate()` gains a second
lookup step:

```python
def authenticate(self, username=None, password=None, **kwargs):
    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(email=username)
    except UserModel.DoesNotExist:
        try:
            user = UserModel.objects.get(voter__sin=username)
        except UserModel.DoesNotExist:
            return None
    if user.check_password(password):
        return user
    return None
```

Tries the typed value as an email first (admins), then as a `Voter.sin`
(students). One shared login form and field, no UI change — the backend
transparently accepts either.

## CSV import feature

**Route:** `administrator/voters/import` (new view + URL, following the
existing `administrator` app's patterns for voter-related pages).

**Template:** an upload form (`<input type="file">` + submit) rendering a
results summary after processing, in the same page.

**Expected columns:** `SN, SIN, NAME, NRC` — header row required,
case-insensitive match on header names. `SN` is read and ignored (it's
just the sheet's row number).

**Per-row processing:**

1. **Name split:** `NAME.split(' ', 1)` — everything before the first
   space is the first name, everything after is the last name. A NAME
   with no space at all is treated as first name only (last name empty).
2. **NRC normalization:** strip every character that isn't a digit
   (`re.sub(r'\D', '', nrc)`), so `468764/34/2`, `468764342`, and any
   other punctuation/spacing variant all normalize to the same digit
   string. Take the last 4 digits.
3. **Password generation:** first 3 letters of the first name, capitalized
   first letter + lowercase rest (e.g. `Isaac` → `Isa`; a 2-letter name
   like `Al` → `Al`, i.e. take what's there, don't pad or error), a
   literal hyphen, then the last-4-digits from step 2. Example:
   `NAME="Isaac Zimba"`, `NRC="468764/34/2"` → password `Isa-4342`.
4. **Row validation** — a row is **skipped** (not fatal to the rest of the
   import) if any of:
   - `SIN` is missing/blank.
   - `SIN` already exists in the `Voter` table (already imported —
     this is what makes re-upload idempotent).
   - `NAME` is missing/blank.
   - `NRC`, after stripping non-digits, has fewer than 4 digits.
5. **On success:** create `CustomUser` (`user_type=2`, `first_name`,
   `last_name`, placeholder `email`, `password=make_password(generated)`)
   and `Voter` (`admin=<that user>`, `sin=<SIN>`, `phone` left blank) in
   one atomic transaction per row.

**Results page:** counts of created vs. skipped rows, and for each skipped
row: the row's SN/SIN (whichever is available) and the specific reason
(e.g. "Row 14: duplicate SIN", "Row 22: NRC has only 2 digits").

## Testing / verification plan

- Unit-style verification via Django shell (matching this project's
  existing lack of a formal test suite — no test framework changes are in
  scope here): construct the exact `Isaac Zimba` / `468764/34/2` example
  and confirm the generated password is `Isa-4342`.
- Verify NRC normalization against both a slashed (`468764/34/2`) and
  unslashed (`468764342`) input produce the same last-4-digits result.
- Upload a small CSV (3-4 rows: one normal, one with a slash-free NRC, one
  with a duplicate SIN, one with a missing NRC) through the real admin
  page against a running Docker instance, and confirm the results page
  reports exactly the expected created/skipped split with correct reasons.
- Confirm a created student account can then log in with `SIN` + the
  generated password on the real login form, and lands on the voter
  dashboard (not admin).
- Confirm re-uploading the same CSV a second time skips all rows as
  duplicates and creates nothing new.
- Confirm existing admin login (by email) and existing self-registration
  (`account_register`) are both unaffected.

## Security note (carried forward, not a blocker)

The generated password is derivable from a student's name and NRC, both of
which may be known to others on campus (e.g. via a class roster). This is
an accepted tradeoff for this iteration per explicit decision — no forced
password change is being added now. Worth revisiting if this becomes a
real concern later.
