# Password Management for Admins and Voters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin/superadmin reset any voter's password from the existing Edit Voter modal, and let any admin/superadmin change their own password from a new dedicated page.

**Architecture:** Task 1 rewrites `updateVoter` (currently a broken `ModelForm`-based view with no password field and a mislabeled SIN field bound to `email`) the same way `voters` (Add Voter) was rewritten earlier this session — read POST fields directly, no `CustomUserForm`/`VoterForm`. Task 2 adds one new self-contained view + template + URL + sidebar link for changing your own password, using Django's built-in `check_password`/`set_password`/`update_session_auth_hash`.

**Tech Stack:** Django (this project's existing stack) — no new dependencies, no model/migration changes in either task.

## Global Constraints

- No model or migration changes in this plan — both tasks are view/template only, safe to deploy against the live production database without any data risk.
- This project has no formal test suite (`administrator/tests.py`, `account/tests.py`, `voting/tests.py` are all empty Django stubs) — verify every task with real `python manage.py shell -c "..."` runs against a throwaway SQLite database, matching this project's established convention (see prior plans in `docs/superpowers/plans/`). Do not introduce pytest or a new test framework.
- Never touch or stage the untracked file `CUEA VOTER'S REGISTRATION .csv` in the repo root — it contains real student PII and must never be committed.
- When staging changes, add files by exact name (`git add <path>`), never `git add -A` or `git add .` — this repo has untracked PII and local venv artifacts that must never be swept in.
- Password fields introduce no new complexity/strength validation beyond "must not be empty" — consistent with the rest of this app (bulk-imported passwords are just digits from an NRC).

---

### Task 1: Admin resets a voter's password (fix Edit Voter)

**Files:**
- Modify: `administrator/views.py` (`updateVoter` function, `view_voter_by_id` function, remove now-unused `CustomUserForm` import)
- Modify: `administrator/templates/admin/voters.html` (Edit modal fields + `getRow()` JS)

**Interfaces:**
- Consumes: `Voter` model (`voting/models.py`) — `sin` (unique, nullable `CharField`), `phone` (unique, nullable `CharField`), `admin` (`OneToOneField` to `CustomUser`). `CustomUser.set_password()` (Django built-in).
- Produces: nothing new consumed by Task 2 — these tasks are independent.

- [ ] **Step 1: Rewrite the `updateVoter` view**

In `administrator/views.py`, find the current `updateVoter` function:

```python
def updateVoter(request):
    if request.method != 'POST':
        messages.error(request, "Access Denied")
        return redirect(reverse('adminViewVoters'))

    try:
        instance = Voter.objects.get(id=request.POST.get('id'))
        user = CustomUserForm(request.POST or None, instance=instance.admin)
        voter = VoterForm(request.POST or None, instance=instance)

        if user.is_valid() and voter.is_valid():
            # Append @gmail.com if not already present
            email = user.cleaned_data['email']
            if not email.endswith('@gmail.com'):
                email += '@gmail.com'
            user.instance.email = email

            user.save()
            voter.save()
            messages.success(request, "Voter's bio updated")
        else:
            messages.error(request, "Form validation failed")

    except Voter.DoesNotExist:
        messages.error(request, "Voter not found")
    except Exception as e:
        messages.error(request, f"Access To This Resource Denied: {e}")

    return redirect(reverse('adminViewVoters'))
```

Replace it with:

```python
def updateVoter(request):
    if request.method != 'POST':
        messages.error(request, "Access Denied")
        return redirect(reverse('adminViewVoters'))

    try:
        voter = Voter.objects.get(id=request.POST.get('id'))
    except Voter.DoesNotExist:
        messages.error(request, "Voter not found")
        return redirect(reverse('adminViewVoters'))

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    sin = request.POST.get('sin', '').strip()
    phone = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()

    if not first_name or not last_name or not sin:
        messages.error(request, "First name, last name and SIN are required")
    elif Voter.objects.filter(sin=sin).exclude(id=voter.id).exists():
        messages.error(request, f"A voter with SIN {sin} already exists")
    else:
        try:
            with transaction.atomic():
                user = voter.admin
                user.first_name = first_name
                user.last_name = last_name
                if password:
                    user.set_password(password)
                user.save()

                voter.sin = sin
                voter.phone = phone or None
                voter.save()
            messages.success(request, "Voter's bio updated")
        except Exception:
            messages.error(
                request, "Could not update voter - the phone number may already be in use")

    return redirect(reverse('adminViewVoters'))
```

Also delete the commented-out dead code directly above it (the old, already-disabled version of this same function):

```python
# def updateVoter(request):
#     if request.method != 'POST':
#         messages.error(request, "Access Denied")
#     try:
#         instance = Voter.objects.get(id=request.POST.get('id'))
#         user = CustomUserForm(request.POST or None, instance=instance.admin)
#         voter = VoterForm(request.POST or None, instance=instance)
#         user.save()
#         voter.save()
#         messages.success(request, "Voter's bio updated")
#     except:
#         messages.error(request, "Access To This Resource Denied")

#     return redirect(reverse('adminViewVoters'))
```
(Delete this whole block — replace it with nothing.)

- [ ] **Step 2: Remove the now-unused `CustomUserForm` import**

`updateVoter` was the last remaining use of `CustomUserForm` in this file (the `voters`/Add Voter view already stopped using it earlier this session). Find near the top of `administrator/views.py`:

```python
from account.forms import CustomUserForm
```

Delete this line entirely. Leave `from voting.forms import *` alone — `PositionForm` and `CandidateForm` from that same wildcard import are still used elsewhere in this file.

- [ ] **Step 3: Fix `view_voter_by_id` to return the real SIN**

Find:

```python
def view_voter_by_id(request):
    voter_id = request.GET.get('id', None)
    voter = Voter.objects.filter(id=voter_id)
    context = {}
    if not voter.exists():
        context['code'] = 404
    else:
        context['code'] = 200
        voter = voter[0]
        context['first_name'] = voter.admin.first_name
        context['last_name'] = voter.admin.last_name
        context['phone'] = voter.phone
        context['id'] = voter.id
        context['SIN'] = voter.admin.email
    return JsonResponse(context)
```

Replace the last line inside the `else` block:

```python
        context['sin'] = voter.sin
```

(Just lower-cases the key and points it at `voter.sin` instead of `voter.admin.email` — matches the lowercase style of every other key in this dict, and this key was never actually consumed correctly by the frontend before — see Step 5.)

- [ ] **Step 4: Fix the Edit Voter modal in the template**

In `administrator/templates/admin/voters.html`, find the Edit modal's SIN field:

```html
              <div class="form-group">
                <label for="edit_email" class="col-sm-3 control-label">SIN</label>

                <div class="col-sm-9">
                  <input type="email" class="form-control" id="edit_email" name="email">
                </div>
            </div>
            <div class="form-group">
              <label for="edit_phone" class="col-sm-3 control-label">Phone</label>

              <div class="col-sm-9">
                <input type="text" class="form-control" id="edit_phone" name="phone">
              </div>
          </div> 


          </div>
```

Replace with:

```html
              <div class="form-group">
                <label for="edit_sin" class="col-sm-3 control-label">SIN</label>

                <div class="col-sm-9">
                  <input type="text" class="form-control" id="edit_sin" name="sin">
                </div>
            </div>
            <div class="form-group">
              <label for="edit_phone" class="col-sm-3 control-label">Phone</label>

              <div class="col-sm-9">
                <input type="text" class="form-control" id="edit_phone" name="phone">
              </div>
          </div>
          <div class="form-group">
            <label for="edit_password" class="col-sm-3 control-label">Password</label>

            <div class="col-sm-9">
              <input type="password" class="form-control" id="edit_password" name="password" placeholder="Leave blank to keep current password">
            </div>
          </div>


          </div>
```

- [ ] **Step 5: Fix the `getRow()` JS to populate SIN correctly**

In the same file's `custom_js` block, find:

```javascript
  function getRow(id) {
      $.ajax({
          type: 'GET',
          url: '{% url "viewVoter" %}',
          data: {
              id: id
          },
          dataType: 'json',
          success: function(response) {
              $('.id').val(response.id);
              $('#edit_firstname').val(response.first_name);
              $('#edit_lastname').val(response.last_name);
              $('#edit_phone').val(response.phone);
              $('#edit_email').val(response.email);
              $('.fullname').html(response.first_name + ' ' + response.last_name);
          }
      });
  }
```

Replace with:

```javascript
  function getRow(id) {
      $.ajax({
          type: 'GET',
          url: '{% url "viewVoter" %}',
          data: {
              id: id
          },
          dataType: 'json',
          success: function(response) {
              $('.id').val(response.id);
              $('#edit_firstname').val(response.first_name);
              $('#edit_lastname').val(response.last_name);
              $('#edit_phone').val(response.phone);
              $('#edit_sin').val(response.sin);
              $('#edit_password').val('');
              $('.fullname').html(response.first_name + ' ' + response.last_name);
          }
      });
  }
```

(`response.email` never matched any key the backend actually returned — Step 3 named the key `sin`; also explicitly clears the password field each time the modal opens, so a previously-typed password from an earlier edit can never linger and get resubmitted by accident.)

- [ ] **Step 6: Verify with a throwaway SQLite database**

```bash
rm -f /tmp/plan_edit_voter_test.sqlite3
SECRET_KEY=test-key DATABASE_URL=sqlite:////tmp/plan_edit_voter_test.sqlite3 ALLOWED_HOSTS=testserver python manage.py migrate --noinput
SECRET_KEY=test-key DATABASE_URL=sqlite:////tmp/plan_edit_voter_test.sqlite3 ALLOWED_HOSTS=testserver python manage.py shell -c "
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
from account.models import CustomUser
from voting.models import Voter

admin = CustomUser.objects.create_user(email='admin@test.local', password='adminpass', first_name='Ad', last_name='Min', user_type=1)
voter_user = CustomUser.objects.create_user(email='v1@students.local', password='oldpass123', first_name='Old', last_name='Name', user_type=2)
voter = Voter.objects.create(admin=voter_user, sin='11112222')

def real_login(username, password):
    c = Client()
    resp = c.post('/account/', {'email': username, 'password': password}, follow=True)
    return resp.wsgi_request.user.is_authenticated

print('1) old password logs in before any edit:', real_login('11112222', 'oldpass123'))

admin_client = Client()
admin_client.force_login(admin)

# Edit with blank password - old password should keep working
resp = admin_client.post('/administrator/voters/update', {
    'id': voter.id, 'first_name': 'New', 'last_name': 'Name', 'sin': '11112222', 'phone': '', 'password': '',
}, follow=True)
print('2) edit (blank password) status:', resp.status_code, [str(m) for m in resp.context['messages']])
print('3) old password STILL works after blank-password edit:', real_login('11112222', 'oldpass123'))

# Edit with a new password - old should stop working, new should work
resp = admin_client.post('/administrator/voters/update', {
    'id': voter.id, 'first_name': 'New', 'last_name': 'Name', 'sin': '11112222', 'phone': '', 'password': 'brandnewpass',
}, follow=True)
print('4) edit (new password) status:', resp.status_code, [str(m) for m in resp.context['messages']])
print('5) old password now FAILS:', real_login('11112222', 'oldpass123'))
print('6) new password WORKS:', real_login('11112222', 'brandnewpass'))

# Duplicate SIN rejected
other_user = CustomUser.objects.create_user(email='v2@students.local', password='pw2', first_name='Other', last_name='Voter', user_type=2)
other_voter = Voter.objects.create(admin=other_user, sin='99998888')
resp = admin_client.post('/administrator/voters/update', {
    'id': voter.id, 'first_name': 'New', 'last_name': 'Name', 'sin': '99998888', 'phone': '', 'password': '',
}, follow=True)
print('7) duplicate SIN edit status:', resp.status_code, [str(m) for m in resp.context['messages']])
voter.refresh_from_db()
print('8) SIN unchanged after rejected duplicate edit:', voter.sin == '11112222')

# view_voter_by_id returns sin correctly
resp = admin_client.get('/administrator/voters/view', {'id': voter.id})
print('9) view_voter_by_id JSON:', resp.json())
"
rm -f /tmp/plan_edit_voter_test.sqlite3
```

Expected output:
```
1) old password logs in before any edit: True
2) edit (blank password) status: 200 [\"Voter's bio updated\"]
3) old password STILL works after blank-password edit: True
4) edit (new password) status: 200 [\"Voter's bio updated\"]
5) old password now FAILS: False
6) new password WORKS: True
7) duplicate SIN edit status: 200 ['A voter with SIN 99998888 already exists']
8) SIN unchanged after rejected duplicate edit: True
9) view_voter_by_id JSON: {'code': 200, 'first_name': 'New', 'last_name': 'Name', 'phone': None, 'id': ..., 'sin': '11112222'}
```
(The `id` value in line 9 will be whatever integer was auto-assigned - just confirm `'sin': '11112222'` is present and correct, and that there's no `'SIN'` or `'email'` key.)

If your local environment doesn't already have Django installed, bootstrap a throwaway venv first:
```bash
python3 -m venv /tmp/plan_venv
/tmp/plan_venv/bin/pip install -q django dj-database-url psycopg2-binary Pillow whitenoise django-renderpdf requests
```
and prefix every `python manage.py ...` command above with `/tmp/plan_venv/bin/python` instead of `python`.

- [ ] **Step 7: Commit**

```bash
git add administrator/views.py administrator/templates/admin/voters.html
git commit -m "Fix admin unable to reset a voter's SIN/password via Edit Voter"
```

---

### Task 2: Admin/Superadmin changes their own password

**Files:**
- Modify: `administrator/views.py` (append new `change_password` view, add `update_session_auth_hash` import)
- Modify: `administrator/urls.py` (add new route)
- Modify: `administrator/templates/sidebar.html` (add nav link)
- Create: `administrator/templates/admin/change_password.html`

**Interfaces:**
- Consumes: `request.user.check_password()`, `request.user.set_password()` (Django `AbstractBaseUser` built-ins), `django.contrib.auth.update_session_auth_hash`.
- Produces: URL name `changePassword` at `/administrator/settings/change-password` — consumed by the new sidebar link only (no other task depends on this).

- [ ] **Step 1: Add the `update_session_auth_hash` import**

Near the top of `administrator/views.py`, find:

```python
from django.contrib import messages
```

Add directly below it:

```python
from django.contrib.auth import update_session_auth_hash
```

- [ ] **Step 2: Add the `change_password` view**

Append to the end of `administrator/views.py`:

```python
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect")
        elif not new_password:
            messages.error(request, "New password is required")
        elif new_password != confirm_password:
            messages.error(request, "New password and confirmation do not match")
        else:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password changed successfully")

    context = {
        'page_title': 'Change Password',
    }
    return render(request, "admin/change_password.html", context)
```

- [ ] **Step 3: Add the URL route**

In `administrator/urls.py`, find:

```python
    path('admin/reset-backup', views.reset_backup, name='resetBackup'),
```

Add directly below it:

```python
    path('settings/change-password', views.change_password, name='changePassword'),
```

- [ ] **Step 4: Create the template**

Create `administrator/templates/admin/change_password.html`:

```html
{% extends 'root.html' %}
{% block content %}
<section class="content">
  <div class="row">
    <div class="col-xs-12">
      <div class="box">
        <div class="box-header with-border">
          <h3 class="box-title">Change Password</h3>
        </div>
        <div class="box-body">
          <form method="POST">
            {% csrf_token %}
            <div class="form-group">
              <label for="current_password">Current Password</label>
              <input type="password" class="form-control" name="current_password" id="current_password" required>
            </div>
            <div class="form-group">
              <label for="new_password">New Password</label>
              <input type="password" class="form-control" name="new_password" id="new_password" required>
            </div>
            <div class="form-group">
              <label for="confirm_password">Confirm New Password</label>
              <input type="password" class="form-control" name="confirm_password" id="confirm_password" required>
            </div>
            <button type="submit" class="btn btn-success btn-flat"><i class="fa fa-key"></i> Change Password</button>
          </form>
        </div>
      </div>
    </div>
  </div>
</section>
{% endblock content %}
```

- [ ] **Step 5: Add the sidebar link**

In `administrator/templates/sidebar.html`, find:

```html
      <li class=""><a href="{% url 'ballot_position' %}"><i class="fa fa-file-text"></i> <span>Ballot Position</span></a></li>
      <li class=""><a href="#config" data-toggle="modal"><i class="fa fa-font"></i> <span>Election Title</span></a></li>
            
      {% endif %}
```

Replace with:

```html
      <li class=""><a href="{% url 'ballot_position' %}"><i class="fa fa-file-text"></i> <span>Ballot Position</span></a></li>
      <li class=""><a href="#config" data-toggle="modal"><i class="fa fa-font"></i> <span>Election Title</span></a></li>
      <li class=""><a href="{% url 'changePassword' %}"><i class="fa fa-key"></i> <span>Change Password</span></a></li>
            
      {% endif %}
```
(This sits inside the existing `{% if request.user.user_type == '0' or request.user.user_type == '1' %}` block already wrapping the SETTINGS section — both Admin and Superadmin see it, no new gate needed.)

- [ ] **Step 6: Verify with a throwaway SQLite database**

```bash
rm -f /tmp/plan_change_pw_test.sqlite3
SECRET_KEY=test-key DATABASE_URL=sqlite:////tmp/plan_change_pw_test.sqlite3 ALLOWED_HOSTS=testserver python manage.py migrate --noinput
SECRET_KEY=test-key DATABASE_URL=sqlite:////tmp/plan_change_pw_test.sqlite3 ALLOWED_HOSTS=testserver python manage.py shell -c "
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
from account.models import CustomUser

admin = CustomUser.objects.create_user(email='admin@test.local', password='originalpass', first_name='Ad', last_name='Min', user_type=1)

client = Client()
client.force_login(admin)

# Wrong current password - rejected, nothing changes
resp = client.post('/administrator/settings/change-password', {
    'current_password': 'wrongpass', 'new_password': 'newpass123', 'confirm_password': 'newpass123',
}, follow=True)
print('1) wrong current password status:', resp.status_code, [str(m) for m in resp.context['messages']])
admin.refresh_from_db()
print('2) password unchanged after rejection:', admin.check_password('originalpass'))

# Mismatched confirmation - rejected
resp = client.post('/administrator/settings/change-password', {
    'current_password': 'originalpass', 'new_password': 'newpass123', 'confirm_password': 'different',
}, follow=True)
print('3) mismatched confirmation status:', resp.status_code, [str(m) for m in resp.context['messages']])
admin.refresh_from_db()
print('4) password unchanged after mismatch:', admin.check_password('originalpass'))

# Correct current password, matching new/confirm - succeeds, session survives
resp = client.post('/administrator/settings/change-password', {
    'current_password': 'originalpass', 'new_password': 'newpass123', 'confirm_password': 'newpass123',
}, follow=True)
print('5) successful change status:', resp.status_code, [str(m) for m in resp.context['messages']])
print('6) session survived (no forced logout):', resp.wsgi_request.user.is_authenticated)
admin.refresh_from_db()
print('7) new password now works:', admin.check_password('newpass123'))
print('8) old password no longer works:', admin.check_password('originalpass'))

# Confirm the new password works on a genuinely fresh login too
def real_login(username, password):
    c = Client()
    r = c.post('/account/', {'email': username, 'password': password}, follow=True)
    return r.wsgi_request.user.is_authenticated

print('9) fresh login with new password:', real_login('admin@test.local', 'newpass123'))
print('10) fresh login with old password fails:', real_login('admin@test.local', 'originalpass'))
"
rm -f /tmp/plan_change_pw_test.sqlite3
```

Expected output:
```
1) wrong current password status: 200 ['Current password is incorrect']
2) password unchanged after rejection: True
3) mismatched confirmation status: 200 ['New password and confirmation do not match']
4) password unchanged after mismatch: True
5) successful change status: 200 ['Password changed successfully']
6) session survived (no forced logout): True
7) new password now works: True
8) old password no longer works: False
9) fresh login with new password: True
10) fresh login with old password fails: False
```

If your local environment doesn't already have Django installed, bootstrap a throwaway venv first:
```bash
python3 -m venv /tmp/plan_venv
/tmp/plan_venv/bin/pip install -q django dj-database-url psycopg2-binary Pillow whitenoise django-renderpdf requests
```
and prefix every `python manage.py ...` command above with `/tmp/plan_venv/bin/python` instead of `python`.

- [ ] **Step 7: Commit**

```bash
git add administrator/views.py administrator/urls.py administrator/templates/sidebar.html administrator/templates/admin/change_password.html
git commit -m "Add self-service Change Password page for Admin/Superadmin"
```
