import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db  # noqa: E402

STRONG_PASSWORD = "StrongP@ss!2026"


@pytest.fixture()
def client():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app.test_client()


def register(client, email="a@example.com", password=STRONG_PASSWORD):
    return client.post("/register", data={
        "name": "Asha Test", "email": email, "password": password, "confirm": password,
    }, follow_redirects=True)


def category_id(client, kind, name):
    from models import Category
    with client.application.app_context():
        return Category.query.filter_by(type=kind, name=name).first().id


def test_auth_flow(client):
    assert client.get("/dashboard").status_code == 302  # login required
    weak = client.post("/register", data={
        "name": "Asha Test",
        "email": "weak@example.com",
        "password": "secret1",
        "confirm": "secret1",
    }, follow_redirects=True)
    assert b"at least 8 characters" in weak.data

    assert b"Your account is ready" in register(client).data
    client.post("/logout")
    bad = client.post("/login", data={"email": "a@example.com", "password": "wrong"})
    assert b"Invalid email or password" in bad.data
    ok = client.post("/login", data={"email": "a@example.com", "password": STRONG_PASSWORD}, follow_redirects=True)
    assert b"Dashboard" in ok.data


def test_crud_and_reports(client):
    register(client)
    from datetime import date
    today = date.today().isoformat()
    salary = category_id(client, "income", "Salary")
    food = category_id(client, "expense", "Food & Dining")

    client.post("/transactions/add", data={"type": "income", "amount": "50000", "category_id": salary, "date": today, "description": "Pay"})
    client.post("/transactions/add", data={"type": "expense", "amount": "1200.50", "category_id": food, "date": today, "description": "Lunch"})

    dash = client.get("/dashboard").data.decode()
    assert "50,000.00" in dash and "1,200.50" in dash and "48,799.50" in dash

    # category must match type
    bad = client.post("/transactions/add", data={"type": "income", "amount": "5", "category_id": food, "date": today})
    assert b"matches the transaction type" in bad.data

    # edit
    client.post("/transactions/2/edit", data={"type": "expense", "amount": "900", "category_id": food, "date": today, "description": "Cheaper lunch"})
    assert "Cheaper lunch" in client.get("/transactions").data.decode()
    assert "49,100.00" in client.get("/dashboard").data.decode()

    report = client.get("/report").data.decode()
    assert "Savings rate" in report and "98.2%" in report

    # delete
    client.post("/transactions/2/delete")
    assert "Cheaper lunch" not in client.get("/transactions").data.decode()


def test_users_are_isolated(client):
    register(client, "a@example.com")
    from datetime import date
    client.post("/transactions/add", data={"type": "expense", "amount": "10", "category_id": category_id(client, "expense", "Rent"), "date": date.today().isoformat()})
    client.post("/logout")
    register(client, "b@example.com")
    assert client.get("/transactions/1/edit").status_code == 404
    assert client.post("/transactions/1/delete").status_code == 404
