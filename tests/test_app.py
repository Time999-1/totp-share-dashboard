import os
import tempfile

os.environ["FLASK_TESTING"] = "1"
os.environ["SESSION_SECRET"] = "test-session-secret-that-is-long-enough"
os.environ["APP_ENCRYPTION_KEY"] = "test-encryption-key-that-is-long-enough"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"

import pyotp

from app import Vehicle, create_app, db, encrypt_text, token_hash


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
        assert client.get("/admin").status_code == 200
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
