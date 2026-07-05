import os
import sqlite3
import tempfile
from datetime import date, timedelta

os.environ["FLASK_TESTING"] = "1"
os.environ["SESSION_SECRET"] = "test-session-secret-that-is-long-enough"
os.environ["APP_ENCRYPTION_KEY"] = "test-encryption-key-that-is-long-enough"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

import pyotp
from sqlalchemy import text

from app import Admin, Category, Vehicle, create_app, db, decrypt_text, encrypt_text, token_hash


def make_app():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
        }
    )
    return app, path


def login(client):
    return client.post("/login", data={"username": "admin", "password": "test-admin-password"})


def test_login_and_admin_page():
    app, path = make_app()
    try:
        client = app.test_client()
        response = login(client)
        assert response.status_code == 302
        page = client.get("/admin")
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        assert "搜索名称、编号或账号" in html
        assert 'data-theme-value="light"' in html
        assert 'data-theme-value="dark"' in html
        assert 'data-theme-value="system"' in html
        assert client.get("/login").headers["Referrer-Policy"] == "same-origin"
    finally:
        os.unlink(path)


def test_share_link_returns_current_totp_and_can_be_disabled():
    app, path = make_app()
    try:
        token = "a" * 32
        secret = pyotp.random_base32()
        with app.app_context():
            vehicle = Vehicle(
                name="18车",
                code="018",
                secret_cipher=encrypt_text(secret),
                share_token_cipher=encrypt_text(token),
                share_token_hash=token_hash(token),
            )
            db.session.add(vehicle)
            db.session.commit()
            vehicle_id = vehicle.id

        client = app.test_client()
        assert client.get(f"/s/{token}").status_code == 200
        payload = client.get(f"/api/s/{token}/code").get_json()
        assert payload["code"] == pyotp.TOTP(secret).now()
        assert payload["vehicle_code"] == "018"

        login(client)
        client.post(f"/admin/vehicles/{vehicle_id}/toggle")
        assert client.get(f"/s/{token}").status_code == 404
    finally:
        os.unlink(path)


def test_create_vehicle_rejects_invalid_secret():
    app, path = make_app()
    try:
        client = app.test_client()
        login(client)
        response = client.post(
            "/admin/vehicles",
            data={"name": "1车", "code": "001", "secret": "not-a-valid-secret"},
            follow_redirects=True,
        )
        assert "保存失败" in response.get_data(as_text=True)
        with app.app_context():
            assert Vehicle.query.count() == 0
    finally:
        os.unlink(path)


def test_new_share_links_use_compact_tokens():
    app, path = make_app()
    try:
        client = app.test_client()
        login(client)
        response = client.post(
            "/admin/vehicles",
            data={"name": "2车", "code": "002", "secret": pyotp.random_base32()},
        )
        assert response.status_code == 302
        with app.app_context():
            vehicle = Vehicle.query.filter_by(code="002").one()
            token = decrypt_text(vehicle.share_token_cipher)
            assert len(token) == 12
        assert client.get(f"/s/{token}").status_code == 200
    finally:
        os.unlink(path)


def test_admin_password_can_be_reset_from_cli():
    app, path = make_app()
    try:
        runner = app.test_cli_runner()
        result = runner.invoke(
            args=["reset-admin-password"],
            input="new-test-password-123\nnew-test-password-123\n",
        )
        assert result.exit_code == 0
        assert "管理员密码已更新" in result.output
        client = app.test_client()
        response = client.post(
            "/login",
            data={"username": "admin", "password": "new-test-password-123"},
        )
        assert response.status_code == 302
        with app.app_context():
            assert Admin.query.one().username == "admin"
    finally:
        os.unlink(path)


def test_categories_and_membership_fields():
    app, path = make_app()
    try:
        client = app.test_client()
        login(client)
        response = client.post(
            "/admin/categories",
            data={"name": "ChatGPT", "color": "blue"},
        )
        assert response.status_code == 302
        assert client.get("/admin/categories").status_code == 200
        expiry = (date.today() + timedelta(days=5)).isoformat()
        response = client.post(
            "/admin/vehicles",
            data={
                "name": "ChatGPT会员",
                "code": "003",
                "category": "ChatGPT",
                "account": "member@example.com",
                "expires_at": expiry,
                "notes": "测试备注",
                "secret": pyotp.random_base32(),
            },
        )
        assert response.status_code == 302
        with app.app_context():
            vehicle = Vehicle.query.filter_by(code="003").one()
            vehicle_id = vehicle.id
            assert vehicle.category == "ChatGPT"
            assert vehicle.account == "member@example.com"
            assert vehicle.notes == "测试备注"
            assert vehicle.expires_at.isoformat() == expiry
            category = Category.query.filter_by(name="ChatGPT").one()
            category_id = category.id
        assert "member-card" in client.get("/admin").get_data(as_text=True)
        assert client.get(f"/admin/vehicles/{vehicle_id}/edit").status_code == 200
        response = client.post(
            f"/admin/categories/{category_id}/update",
            data={"name": "ChatGPT Plus", "color": "purple"},
        )
        assert response.status_code == 302
        with app.app_context():
            assert Vehicle.query.filter_by(code="003").one().category == "ChatGPT Plus"
    finally:
        os.unlink(path)


def test_existing_database_is_migrated():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        connection = sqlite3.connect(path)
        connection.execute(
            """
            CREATE TABLE vehicle (
              id INTEGER PRIMARY KEY,
              name VARCHAR(80) NOT NULL,
              code VARCHAR(20) NOT NULL UNIQUE,
              secret_cipher TEXT NOT NULL,
              share_token_cipher TEXT NOT NULL,
              share_token_hash VARCHAR(64) NOT NULL UNIQUE,
              enabled BOOLEAN NOT NULL DEFAULT 1,
              created_at DATETIME NOT NULL
            )
            """
        )
        connection.commit()
        connection.close()
        app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "SESSION_COOKIE_SECURE": False,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
            }
        )
        with app.app_context():
            columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(vehicle)"))}
            assert {"category", "account", "expires_at", "notes"} <= columns
            assert Category.query.filter_by(name="未分类").one()
    finally:
        os.unlink(path)
