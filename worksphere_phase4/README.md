# WorkSphere HRMS - Phase 4: Employee Experience & System Integrations

FastAPI + SQLAlchemy 2 + Pydantic v2 backend with a dependency-free JavaScript frontend (served by the API at `/app/`).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then set SECRET_KEY (see the file for the command)
python seed.py                                          # creates tables + demo admin/HR/employee (passwords printed once)
uvicorn app.main:app --reload
```

- App UI: http://localhost:8000/app/
- Interactive API docs: http://localhost:8000/docs

Tests: `pip install -r requirements-dev.txt && pytest`

## Integrating with your Phase 1-3 code

This package is self-contained so it runs on its own. `User`, `Employee` and `Notification` in `app/models.py`
are minimal versions of your existing tables. If your project already has them, keep yours and make sure these
columns exist: `users(id, email, hashed_password, role, is_active)`, `employees(id, user_id, full_name, phone,
department, designation, date_joined)`, `notifications(id, user_id, title, message, is_read, created_at)`.
Then copy the new models, routers, schemas and services into your project and register the routers in `main.py`.

## Modules

| # | Module | Endpoints (prefix `/api`) | Roles |
|---|--------|---------------------------|-------|
| 21 | Onboarding | `POST /onboarding`, `POST /onboarding/employee/{id}/default-checklist`, `GET /onboarding/me`, `/me/progress`, `/employee/{id}`, `/employee/{id}/progress`, `PATCH /onboarding/{id}/status`, `DELETE` | HR/Admin assign; employee sees and ticks own |
| 22 | Resignation & exit | `POST /resignations`, `GET /resignations/me`, `GET /resignations`, `PATCH /resignations/{id}/decision`, `DELETE /resignations/{id}` (withdraw) | Employee submits; HR/Admin decide |
| 23 | Announcements | `POST/PUT/DELETE /announcements`, `GET /announcements`, `GET /announcements/{id}` | HR/Admin write; everyone reads |
| 24 | Tasks | `POST /tasks`, `GET /tasks`, `/tasks/me`, `/tasks/summary`, `PUT /tasks/{id}`, `PATCH /tasks/{id}/status`, `DELETE` | HR/Admin assign; assignee updates status |
| 25 | Integrations | `GET /integrations/export/{report}?format=csv\|pdf`, `GET /integrations/calendar/events`, `/calendar/ics`, `POST /integrations/email/test`, `GET /integrations/status` | Exports: HR/Admin; calendar: any employee |
| 26 | Feedback | `POST /feedback`, `GET /feedback/me`, `GET /feedback`, `GET /feedback/stats` | Employee submits; HR/Admin view |
| 27 | Profile & settings | `GET/PUT /profile`, `POST /profile/change-password`, `GET/PUT /profile/preferences` | Own account only |

Supporting: `POST /auth/login`, `GET /auth/me`, `POST /auth/register` (Admin; auto-assigns the default onboarding checklist), `GET /auth/employees` (HR/Admin dropdown data).

### Notes on behaviour
- **Exit tracking:** `notice_period` is in days. `last_working_day = created_at + notice_period`; `exit_stage` is derived (`UNDER_REVIEW`, `SERVING_NOTICE`, `EXITED`, `REJECTED`) because the table has no approval date.
- **Email:** off by default (`EMAIL_ENABLED=false` just logs). Set the SMTP variables in `.env` to send. Mail is sent in the background and respects each user's notification preferences.
- **Calendar:** exports an `.ics` file and per-event "Add to Google Calendar" links. No OAuth/Google API keys required.
- **Reports:** employees, onboarding, resignations, tasks, feedback, announcements as CSV or PDF (max 5000 rows).

## Security
- JWT bearer auth; the user and role are re-read from the database on every request, so deactivating a user takes effect immediately.
- Role-based authorization via `require_roles` / `require_staff`; ownership validation via `assert_owner_or_staff` (employees can only read or change their own onboarding, tasks, resignations).
- All inputs validated and length-limited with Pydantic; passwords need 8+ chars with upper, lower and a digit; hashed with scrypt.
- App refuses to start without a 32+ character `SECRET_KEY`. No secrets in code; seed passwords are random.
- Login throttling (5 failures / 15 min per email+IP, in-memory - use a shared limiter if you run multiple workers), uniform login errors, CSV formula-injection protection, escaped PDF content, `textContent`-only frontend rendering, strict CSP and security headers.
- The frontend keeps the token in `sessionStorage`. For production, serve over HTTPS and consider httpOnly cookies.
