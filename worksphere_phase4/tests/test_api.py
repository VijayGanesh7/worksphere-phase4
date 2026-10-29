"""End-to-end API tests. Need the full requirements (fastapi, sqlalchemy) plus httpx: pip install -r requirements-dev.txt"""
from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.enums import Role  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Employee, User, UserPreference  # noqa: E402
from app.security import hash_password  # noqa: E402

PW = "Passw0rdA"
FUTURE = (date.today() + timedelta(days=5)).isoformat()


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for email, role, name in [
            ("admin@t.com", Role.ADMIN, "Ada Admin"),
            ("hr@t.com", Role.HR, "Hal HR"),
            ("e1@t.com", Role.EMPLOYEE, "Eve One"),
            ("e2@t.com", Role.EMPLOYEE, "Eli Two"),
        ]:
            u = User(email=email, hashed_password=hash_password(PW), role=role)
            u.employee = Employee(full_name=name, department="Eng")
            u.preferences = UserPreference()
            db.add(u)
        db.commit()
    with TestClient(app) as c:
        yield c


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def emp_id(client, hdr):
    return client.get("/api/auth/me", headers=hdr).json()["employee_id"]


def test_auth_required_and_bad_login(client):
    assert client.get("/api/tasks/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "e1@t.com", "password": "nope"}).status_code == 401


def test_onboarding_flow_and_ownership(client):
    hr, e1, e2 = login(client, "hr@t.com"), login(client, "e1@t.com"), login(client, "e2@t.com")
    id1 = emp_id(client, e1)
    assert client.post("/api/onboarding", headers=e1, json={"employee_id": id1, "task_name": "x", "due_date": FUTURE}).status_code == 403
    r = client.post("/api/onboarding/employee/%d/default-checklist" % id1, headers=hr)
    assert r.status_code == 201 and len(r.json()) == 7
    mine = client.get("/api/onboarding/me", headers=e1).json()
    assert client.patch("/api/onboarding/%d/status" % mine[0]["id"], headers=e1, json={"status": "COMPLETED"}).status_code == 200
    assert client.get("/api/onboarding/me/progress", headers=e1).json()["completed"] == 1
    # another employee must not read or modify it
    assert client.get("/api/onboarding/employee/%d" % id1, headers=e2).status_code == 403
    assert client.patch("/api/onboarding/%d/status" % mine[1]["id"], headers=e2, json={"status": "COMPLETED"}).status_code == 403


def test_resignation_workflow(client):
    hr, e1 = login(client, "hr@t.com"), login(client, "e1@t.com")
    body = {"reason": "Moving to another city", "notice_period": 30}
    r = client.post("/api/resignations", headers=e1, json=body)
    assert r.status_code == 201 and r.json()["exit_stage"] == "UNDER_REVIEW"
    assert client.post("/api/resignations", headers=e1, json=body).status_code == 409
    rid = r.json()["id"]
    assert client.patch("/api/resignations/%d/decision" % rid, headers=e1, json={"status": "APPROVED"}).status_code == 403
    d = client.patch("/api/resignations/%d/decision" % rid, headers=hr, json={"status": "APPROVED"})
    assert d.status_code == 200 and d.json()["exit_stage"] == "SERVING_NOTICE"
    assert client.patch("/api/resignations/%d/decision" % rid, headers=hr, json={"status": "REJECTED"}).status_code == 409
    assert client.patch("/api/resignations/%d/decision" % rid, headers=hr, json={"status": "PENDING"}).status_code == 422


def test_announcements_permissions_and_notifications(client):
    hr, e1 = login(client, "hr@t.com"), login(client, "e1@t.com")
    assert client.post("/api/announcements", headers=e1, json={"title": "t", "message": "m"}).status_code == 403
    r = client.post("/api/announcements", headers=hr, json={"title": "Holiday", "message": "Office closed Friday"})
    assert r.status_code == 201
    assert client.get("/api/announcements", headers=e1).json()[0]["title"] == "Holiday"
    assert client.get("/api/announcements/%d" % r.json()["id"], headers=e1).status_code == 200
    assert client.delete("/api/announcements/%d" % r.json()["id"], headers=e1).status_code == 403


def test_task_ownership_and_status(client):
    hr, e1, e2 = login(client, "hr@t.com"), login(client, "e1@t.com"), login(client, "e2@t.com")
    id1 = emp_id(client, e1)
    t = client.post("/api/tasks", headers=hr, json={"assigned_to": id1, "title": "Write report", "due_date": FUTURE})
    assert t.status_code == 201
    tid = t.json()["id"]
    assert client.get("/api/tasks/%d" % tid, headers=e2).status_code == 403
    assert client.patch("/api/tasks/%d/status" % tid, headers=e2, json={"status": "COMPLETED"}).status_code == 403
    assert client.patch("/api/tasks/%d/status" % tid, headers=e1, json={"status": "COMPLETED"}).json()["status"] == "COMPLETED"
    assert client.get("/api/tasks", headers=e2).json() == []  # employees only ever see their own
    assert client.get("/api/tasks/summary", headers=hr).json()["completed"] == 1
    assert client.post("/api/tasks", headers=e1, json={"assigned_to": id1, "title": "x", "due_date": FUTURE}).status_code == 403


def test_feedback_validation_and_visibility(client):
    hr, e1 = login(client, "hr@t.com"), login(client, "e1@t.com")
    assert client.post("/api/feedback", headers=e1, json={"message": "ok", "rating": 6}).status_code == 422
    assert client.post("/api/feedback", headers=e1, json={"message": "Good", "rating": 4}).status_code == 201
    assert client.get("/api/feedback", headers=e1).status_code == 403
    assert client.get("/api/feedback", headers=hr).json()[0]["rating"] == 4
    assert client.get("/api/feedback/stats", headers=hr).json()["average_rating"] == 4.0


def test_profile_password_and_preferences(client):
    e1 = login(client, "e1@t.com")
    assert client.put("/api/profile", headers=e1, json={"full_name": "Eve Updated"}).json()["full_name"] == "Eve Updated"
    assert client.post("/api/profile/change-password", headers=e1, json={"current_password": "bad", "new_password": "NewPassw0rd"}).status_code == 400
    assert client.post("/api/profile/change-password", headers=e1, json={"current_password": PW, "new_password": "weak"}).status_code == 422
    assert client.post("/api/profile/change-password", headers=e1, json={"current_password": PW, "new_password": "NewPassw0rd"}).status_code == 204
    assert client.post("/api/auth/login", json={"email": "e1@t.com", "password": "NewPassw0rd"}).status_code == 200
    assert client.put("/api/profile/preferences", headers=e1, json={"email_notifications": False}).json()["email_notifications"] is False


def test_exports_and_calendar(client):
    hr, e1 = login(client, "hr@t.com"), login(client, "e1@t.com")
    csv = client.get("/api/integrations/export/employees?format=csv", headers=hr)
    assert csv.status_code == 200 and "Eve One" in csv.text
    assert client.get("/api/integrations/export/employees?format=pdf", headers=hr).content.startswith(b"%PDF")
    assert client.get("/api/integrations/export/employees", headers=e1).status_code == 403
    assert client.get("/api/integrations/export/nope", headers=hr).status_code == 404
    client.post("/api/tasks", headers=hr, json={"assigned_to": emp_id(client, e1), "title": "Due soon", "due_date": FUTURE})
    ev = client.get("/api/integrations/calendar/events", headers=e1).json()
    assert ev and ev[0]["google_calendar_url"].startswith("https://calendar.google.com/")
    assert b"BEGIN:VCALENDAR" in client.get("/api/integrations/calendar/ics", headers=e1).content


def test_admin_register_creates_default_checklist(client):
    admin, hr = login(client, "admin@t.com"), login(client, "hr@t.com")
    body = {"email": "new@t.com", "password": PW, "full_name": "New Hire"}
    assert client.post("/api/auth/register", headers=hr, json=body).status_code == 403
    assert client.post("/api/auth/register", headers=admin, json=body).status_code == 201
    new = login(client, "new@t.com")
    assert len(client.get("/api/onboarding/me", headers=new).json()) == 7
