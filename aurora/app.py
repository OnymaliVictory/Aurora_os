"""Application factory: wires the database, security and every screen together."""
import os
import sys

from markupsafe import Markup
from flask import Flask, jsonify, redirect, render_template, request, session

from . import __version__, db, license, money, paths, security
from .validate import BadInput


def create_app(testing=False):
    app = Flask(__name__, template_folder=str(paths.app_dir() / "templates"),
                static_folder=str(paths.app_dir() / "static"), static_url_path="/static")
    app.config.update(
        SECRET_KEY=security.secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        TESTING=testing,
        JSON_SORT_KEYS=False,
    )
    db.init_db()
    app.teardown_appcontext(db.close_db)

    # ---------------- helpers available in every template ----------------
    @app.context_processor
    def inject():
        user = security.current_user()
        cfg = db.get_settings(db.get_db()) if user or request.endpoint in ("pages.login", "pages.setup") else {}
        return {
            "me": user, "cfg": cfg, "can": security.can, "csrf": security.csrf_token(),
            "lic_banner": license.banner(db.get_db()) if user else None,
            "nav_all": __import__("aurora.routes.pages", fromlist=["NAV"]).NAV, "version": __version__, "naira": lambda k: money.naira(k, cfg.get("currency_symbol", "₦")),
        }

    @app.template_global()
    def icon(name, cls=""):
        return Markup(f'<svg class="i {cls}" aria-hidden="true"><use href="/static/img/sprite.svg#{name}"/></svg>')

    # Paths that keep working while the subscription is paused (so nothing is ever held hostage).
    OPEN_PATHS = ("/static/", "/login", "/api/login", "/logout", "/setup", "/api/setup", "/license", "/api/license",
                  "/api/me", "/api/notifications", "/api/backups", "/api/products/export.csv", "/api/reports/sales.csv")

    @app.before_request
    def guard():
        if request.endpoint == "static":
            return None
        bad = security.check_csrf()
        if bad is not None:
            return bad
        if license.enabled() and not request.path.startswith(OPEN_PATHS):
            if not license.status(db.get_db())["ok"]:
                if request.path.startswith("/api/") or request.is_json or request.headers.get("X-Requested-With") == "fetch":
                    return jsonify(error="Your Aurora OS subscription has ended, so selling is paused. Renew to continue.", license=True), 402
                return redirect("/license")
            if request.method == "GET" and session.get("uid"):
                license.remind(db.get_db())
        return None

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        # Everything is bundled with the app — nothing is ever loaded from the internet.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'")
        if request.path.startswith("/api/") or request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------- errors: friendly, never a stack trace ----------------
    @app.errorhandler(BadInput)
    def bad_input(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(403)
    def forbidden(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="You do not have permission to do that."), 403
        return render_template("error.html", code=403, title="Not allowed",
                               message="Your account does not have access to this page."), 403

    @app.errorhandler(404)
    def missing(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template("error.html", code=404, title="Page not found",
                               message="That page does not exist."), 404

    @app.errorhandler(400)
    def bad_request(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="That request was not valid. Refresh the page and try again."), 400
        return render_template("error.html", code=400, title="Please try again",
                               message="Your session expired. Go back, refresh the page and try again."), 400

    @app.errorhandler(Exception)
    def crash(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled error")
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on our side. Nothing was saved — please try again."), 500
        return render_template("error.html", code=500, title="Something went wrong",
                               message="Nothing was lost. Please go back and try again."), 500

    # ---------------- screens ----------------
    from .routes import pages, api_catalog, api_pos, api_ops, api_reports
    from .routes import api_license
    for bp in (pages.bp, api_catalog.bp, api_pos.bp, api_ops.bp, api_reports.bp, api_license.bp):
        app.register_blueprint(bp)

    # nightly chores: automatic backup + expiry scan (runs once when the app starts each day)
    if not testing:
        from .services import backup
        backup.run_startup_tasks()
    return app
