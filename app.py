import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from functools import wraps

import pyotp
import click
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["300 per minute"])
SHARE_TOKEN_BYTES = 9  # 72 bits, encoded as a compact 12-character URL-safe token.


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    secret_cipher = db.Column(db.Text, nullable=False)
    share_token_cipher = db.Column(db.Text, nullable=False)
    share_token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id"), nullable=False, index=True)
    ip_address = db.Column(db.String(64), nullable=False)
    user_agent = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    vehicle = db.relationship("Vehicle")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:////app/data/totp.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=os.getenv("SESSION_SECRET", ""),
        APP_ENCRYPTION_KEY=os.getenv("APP_ENCRYPTION_KEY", ""),
        ADMIN_USERNAME=os.getenv("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=3600 * 12,
        RATELIMIT_STORAGE_URI="memory://",
    )
    if test_config:
        app.config.update(test_config)

    if os.getenv("TRUST_PROXY", "true").lower() == "true":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    for key in ("SECRET_KEY", "APP_ENCRYPTION_KEY", "ADMIN_PASSWORD"):
        if not app.config.get(key):
            raise RuntimeError(f"缺少必要环境变量: {key}")

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            db.session.add(
                Admin(
                    username=app.config["ADMIN_USERNAME"],
                    password_hash=generate_password_hash(app.config["ADMIN_PASSWORD"]),
                )
            )
            db.session.commit()

    register_routes(app)
    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("reset-admin-password")
    @click.option(
        "--password",
        prompt="新管理员密码",
        hide_input=True,
        confirmation_prompt="再次输入新密码",
    )
    def reset_admin_password(password):
        """安全地重置管理员密码。"""
        if len(password) < 12:
            raise click.ClickException("密码至少需要12个字符")
        admin = Admin.query.first()
        if not admin:
            raise click.ClickException("未找到管理员账号")
        admin.password_hash = generate_password_hash(password)
        db.session.commit()
        click.echo("管理员密码已更新")


def _fernet():
    raw = current_app_config("APP_ENCRYPTION_KEY").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def current_app_config(name):
    from flask import current_app

    return current_app.config[name]


def encrypt_text(value):
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value):
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("无法解密数据，请确认 APP_ENCRYPTION_KEY 未被修改") from exc


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_share_token():
    return secrets.token_urlsafe(SHARE_TOKEN_BYTES)


def normalize_secret(value):
    secret = "".join(value.split()).upper()
    pyotp.TOTP(secret).now()
    return secret


def current_totp(vehicle):
    now = int(time.time())
    return {
        "code": pyotp.TOTP(decrypt_text(vehicle.secret_cipher)).at(now),
        "remaining": 30 - (now % 30),
    }


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def client_ip():
    if os.getenv("TRUST_PROXY", "true").lower() == "true":
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.remote_addr or "unknown")[:64]


def register_routes(app):
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # Flask-WTF requires a same-origin Referer for HTTPS form submissions.
        # Keep it for this origin while preventing referrer leakage to other sites.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("10 per minute")
    def login():
        if request.method == "POST":
            admin = Admin.query.filter_by(username=request.form.get("username", "").strip()).first()
            if admin and check_password_hash(admin.password_hash, request.form.get("password", "")):
                session.clear()
                session["admin_id"] = admin.id
                session.permanent = True
                return redirect(url_for("admin_dashboard"))
            flash("账号或密码不正确", "error")
        return render_template("login.html")

    @app.post("/logout")
    @admin_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return redirect(url_for("admin_dashboard") if session.get("admin_id") else url_for("login"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        vehicles = Vehicle.query.order_by(Vehicle.code.asc()).all()
        rows = []
        for vehicle in vehicles:
            token = decrypt_text(vehicle.share_token_cipher)
            rows.append(
                {
                    "vehicle": vehicle,
                    "share_url": url_for("share_page", token=token, _external=True),
                }
            )
        today = datetime.now(timezone.utc).date()
        today_views = sum(1 for log in AccessLog.query.all() if log.created_at.date() == today)
        return render_template(
            "admin.html",
            rows=rows,
            active_count=Vehicle.query.filter_by(enabled=True).count(),
            today_views=today_views,
        )

    @app.post("/admin/vehicles")
    @admin_required
    def create_vehicle():
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip()
        try:
            secret = normalize_secret(request.form.get("secret", ""))
            if not name or not code:
                raise ValueError("名称和编号不能为空")
            if Vehicle.query.filter_by(code=code).first():
                raise ValueError("编号已经存在")
            token = generate_share_token()
            db.session.add(
                Vehicle(
                    name=name,
                    code=code,
                    secret_cipher=encrypt_text(secret),
                    share_token_cipher=encrypt_text(token),
                    share_token_hash=token_hash(token),
                )
            )
            db.session.commit()
            flash("车辆已添加，专属链接已生成", "success")
        except Exception as exc:
            db.session.rollback()
            flash(f"保存失败：{exc}", "error")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
    @admin_required
    def edit_vehicle(vehicle_id):
        vehicle = db.get_or_404(Vehicle, vehicle_id)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            code = request.form.get("code", "").strip()
            new_secret = request.form.get("secret", "").strip()
            try:
                if not name or not code:
                    raise ValueError("名称和编号不能为空")
                conflict = Vehicle.query.filter(Vehicle.code == code, Vehicle.id != vehicle.id).first()
                if conflict:
                    raise ValueError("编号已经存在")
                vehicle.name = name
                vehicle.code = code
                if new_secret:
                    vehicle.secret_cipher = encrypt_text(normalize_secret(new_secret))
                db.session.commit()
                flash("资料已更新", "success")
                return redirect(url_for("admin_dashboard"))
            except Exception as exc:
                db.session.rollback()
                flash(f"保存失败：{exc}", "error")
        return render_template("edit.html", vehicle=vehicle)

    @app.post("/admin/vehicles/<int:vehicle_id>/toggle")
    @admin_required
    def toggle_vehicle(vehicle_id):
        vehicle = db.get_or_404(Vehicle, vehicle_id)
        vehicle.enabled = not vehicle.enabled
        db.session.commit()
        flash("分享链接状态已更新", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/vehicles/<int:vehicle_id>/rotate")
    @admin_required
    def rotate_vehicle(vehicle_id):
        vehicle = db.get_or_404(Vehicle, vehicle_id)
        token = generate_share_token()
        vehicle.share_token_cipher = encrypt_text(token)
        vehicle.share_token_hash = token_hash(token)
        vehicle.enabled = True
        db.session.commit()
        flash("已生成新链接，旧链接立即失效", "success")
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/logs")
    @admin_required
    def access_logs():
        logs = AccessLog.query.order_by(AccessLog.created_at.desc()).limit(300).all()
        return render_template("logs.html", logs=logs)

    @app.get("/api/admin/codes")
    @admin_required
    @limiter.limit("120 per minute")
    def admin_codes():
        data = []
        for vehicle in Vehicle.query.order_by(Vehicle.code.asc()).all():
            value = current_totp(vehicle)
            value.update({"id": vehicle.id, "enabled": vehicle.enabled})
            data.append(value)
        return jsonify(data)

    def find_shared_vehicle(token):
        # Accept both the new compact tokens and existing longer tokens.
        if len(token) < 12:
            abort(404)
        vehicle = Vehicle.query.filter_by(share_token_hash=token_hash(token), enabled=True).first()
        if not vehicle:
            abort(404)
        return vehicle

    @app.get("/s/<token>")
    @limiter.limit("60 per minute")
    def share_page(token):
        vehicle = find_shared_vehicle(token)
        db.session.add(
            AccessLog(
                vehicle_id=vehicle.id,
                ip_address=client_ip(),
                user_agent=request.headers.get("User-Agent", "unknown")[:255],
            )
        )
        db.session.commit()
        response = render_template("share.html", vehicle=vehicle, token=token)
        return response

    @app.get("/api/s/<token>/code")
    @limiter.limit("120 per minute")
    def share_code(token):
        vehicle = find_shared_vehicle(token)
        result = current_totp(vehicle)
        result.update({"name": vehicle.name, "vehicle_code": vehicle.code})
        return jsonify(result)


if os.getenv("FLASK_TESTING") == "1":
    app = None
else:
    app = create_app()
