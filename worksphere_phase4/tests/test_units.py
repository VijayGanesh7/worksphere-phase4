"""Framework-free unit tests: schemas, security, exporters, calendar. Need only pydantic, PyJWT, reportlab."""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app import schemas
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.services import calendar_service, exporters


def test_password_hash_roundtrip():
    h = hash_password("Str0ngPass")
    assert h != "Str0ngPass" and verify_password("Str0ngPass", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "garbage")


def test_jwt_roundtrip_and_tamper():
    token = create_access_token(42)
    assert decode_access_token(token)["sub"] == "42"
    assert decode_access_token(token + "x") is None
    assert decode_access_token("not.a.token") is None


@pytest.mark.parametrize("pw", ["short1A", "alllowercase1", "ALLUPPER123", "NoDigitsHere"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(ValidationError):
        schemas.PasswordChange(current_password="x", new_password=pw)


def test_strong_password_ok():
    assert schemas.PasswordChange(current_password="x", new_password="GoodPass1").new_password == "GoodPass1"


def test_onboarding_validation():
    ok = schemas.OnboardingCreate(employee_id=1, task_name="  Read handbook ", due_date=date.today())
    assert ok.task_name == "Read handbook"
    with pytest.raises(ValidationError):
        schemas.OnboardingCreate(employee_id=1, task_name="x", due_date=date.today() - timedelta(days=1))
    with pytest.raises(ValidationError):
        schemas.OnboardingCreate(employee_id=0, task_name="x", due_date=date.today())
    with pytest.raises(ValidationError):
        schemas.OnboardingCreate(employee_id=1, task_name="   ", due_date=date.today())


def test_resignation_validation():
    schemas.ResignationCreate(reason="Relocating to another city", notice_period=30)
    with pytest.raises(ValidationError):
        schemas.ResignationCreate(reason="short", notice_period=30)
    with pytest.raises(ValidationError):
        schemas.ResignationCreate(reason="Relocating to another city", notice_period=999)
    with pytest.raises(ValidationError):
        schemas.ResignationDecision(status="PENDING")
    assert schemas.ResignationDecision(status="APPROVED").status.value == "APPROVED"


def test_feedback_rating_bounds():
    schemas.FeedbackCreate(message="Great place", rating=5)
    for bad in (0, 6, -1):
        with pytest.raises(ValidationError):
            schemas.FeedbackCreate(message="x", rating=bad)


def test_email_and_phone_validation():
    assert schemas.LoginRequest(email=" A@B.com ", password="x").email == "a@b.com"
    with pytest.raises(ValidationError):
        schemas.LoginRequest(email="not-an-email", password="x")
    with pytest.raises(ValidationError):
        schemas.ProfileUpdate(phone="<script>")
    assert schemas.ProfileUpdate(phone="+91 98765-43210").phone


def test_csv_formula_injection_neutralised():
    out = exporters.to_csv(["a"], [["=cmd|' /C calc'!A0"], ["+1"], ["-1"], ["@x"], ["normal"]]).decode("utf-8-sig")
    lines = out.strip().splitlines()[1:]
    assert all(l.startswith("'") for l in lines[:4]) and lines[4] == "normal"


def test_csv_handles_commas_quotes_and_none():
    out = exporters.to_csv(["a", "b"], [['he said "hi", ok', None]]).decode("utf-8-sig")
    assert '"he said ""hi"", ok",' in out


def test_pdf_generation_escapes_markup():
    pdf = exporters.to_pdf("Report <b>", ["Name"], [["<para>&bad</para>"], ["x" * 500]])
    assert pdf.startswith(b"%PDF")


def test_ics_output():
    ics = calendar_service.build_ics(
        [{"uid": "task-1", "title": "Ship; it, now\nplease", "date": date(2026, 11, 5), "kind": "Task"}]
    ).decode()
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261105" in ics and "DTEND;VALUE=DATE:20261106" in ics
    assert "SUMMARY:Ship\\; it\\, now\\nplease" in ics


def test_google_calendar_url():
    url = calendar_service.google_calendar_url("A & B", date(2026, 12, 31))
    assert url.startswith("https://calendar.google.com/calendar/render?")
    assert "20261231%2F20270101" in url and "A+%26+B" in url
