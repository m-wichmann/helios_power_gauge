import hmac
import json
import os
import secrets
import time
from urllib.parse import quote, urlencode, urlsplit

import requests
from flask import Flask, redirect, render_template_string, request, session


AUTHORIZE_URL = "https://connect.solaredge.com/authorize"
TOKEN_URL = "https://monitoringapi.solaredge.com/v2/oauth2/token"

PAGE = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SolarEdge Anmeldung</title>
  <style>
    body { font: 16px system-ui, sans-serif; background: #f3f5f7; color: #24292f;
           display: grid; place-items: center; min-height: 100vh; margin: 0; }
    main { background: white; border-radius: 12px; padding: 2rem; width: min(90%, 32rem);
           box-sizing: border-box; box-shadow: 0 4px 20px #0001; }
    a.button { display: inline-flex; gap: .6rem; align-items: center; background: #c62828;
               color: white; border-radius: 6px; padding: .8rem 1rem; text-decoration: none; }
    svg { width: 1.3rem; height: 1.3rem; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f5f7; padding: 1rem; }
  </style>
</head>
<body><main>
  <h1>SolarEdge Anmeldung</h1>
  {% if message %}<p>{{ message }}</p>{% endif %}
  {% if token %}
    <p>Diese Zugangsdaten nur sicher speichern und nicht weitergeben. Sie werden hier nur einmal angezeigt.</p>
    <pre>{{ token }}</pre>
  {% else %}
    <a class="button" href="{{ url_for('login') }}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/></svg>
      Mit SolarEdge anmelden
    </a>
  {% endif %}
</main></body></html>"""


def create_app():
    required = ("SOLAREDGE_CLIENT_ID", "SOLAREDGE_CLIENT_SECRET",
                "SOLAREDGE_REDIRECT_URI", "FLASK_SECRET_KEY")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Fehlende Umgebungsvariablen: " + ", ".join(missing))

    redirect_uri = os.environ["SOLAREDGE_REDIRECT_URI"]
    uri = urlsplit(redirect_uri)
    if (uri.scheme not in ("http", "https") or not uri.hostname
            or uri.username or uri.password or uri.path not in ("/callback", "/oauth/callback")
            or uri.query or uri.fragment):
        raise RuntimeError("SOLAREDGE_REDIRECT_URI muss eine vollständige URL mit dem Pfad /callback oder /oauth/callback sein.")
    if uri.scheme == "http" and uri.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("HTTP ist nur für lokale Redirect-URIs erlaubt; ansonsten HTTPS verwenden.")
    secret_key = os.environ["FLASK_SECRET_KEY"]
    if len(secret_key) < 32:
        raise RuntimeError("FLASK_SECRET_KEY muss mindestens 32 Zeichen lang sein.")

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=uri.scheme == "https",
    )

    @app.after_request
    def secure_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def index():
        return render_template_string(PAGE)

    @app.get("/login")
    def login():
        state = secrets.token_urlsafe(32)
        session["oauth_state"] = state
        session["oauth_started"] = time.time()
        params = {
            "client_id": os.environ["SOLAREDGE_CLIENT_ID"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "SITE_DATA",
            "state": state,
            "external_id": state,
        }
        return redirect(AUTHORIZE_URL + "?" + urlencode(params, quote_via=quote))

    @app.get("/callback")
    def callback():
        expected = session.pop("oauth_state", None)
        started = session.pop("oauth_started", None)
        state = request.args.get("state")
        external_id = request.args.get("external_id")
        returned = [value for value in (state, external_id) if value is not None]
        if (not isinstance(expected, str) or not isinstance(started, (int, float))
                or not 0 <= time.time() - started <= 600 or not returned
                or any(not hmac.compare_digest(expected.encode(), value.encode()) for value in returned)):
            return render_template_string(PAGE, message="Ungültige oder abgelaufene Anmeldung. Bitte erneut versuchen."), 400
        if request.args.get("error"):
            return render_template_string(PAGE, message="SolarEdge hat die Anmeldung abgelehnt oder abgebrochen."), 400
        code = request.args.get("code")
        if not code:
            return render_template_string(PAGE, message="SolarEdge hat keinen Autorisierungscode zurückgegeben."), 400

        try:
            response = requests.post(
                TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": os.environ["SOLAREDGE_CLIENT_ID"],
                    "client_secret": os.environ["SOLAREDGE_CLIENT_SECRET"],
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException:
            app.logger.error("SolarEdge-Token-Endpunkt nicht erreichbar.")
            return render_template_string(PAGE, message="SolarEdge ist nicht erreichbar. Bitte erneut anmelden."), 502
        if not 200 <= response.status_code < 300:
            app.logger.error("SolarEdge-Token-Endpunkt antwortete mit HTTP %s.", response.status_code)
            return render_template_string(PAGE, message="SolarEdge hat den Token-Austausch abgelehnt. Bitte Konfiguration prüfen und erneut anmelden."), 502
        try:
            token = response.json()
        except ValueError:
            app.logger.error("SolarEdge-Token-Endpunkt lieferte kein gültiges JSON.")
            return render_template_string(PAGE, message="Ungültige Antwort von SolarEdge."), 502
        if not isinstance(token, dict) or not isinstance(token.get("access_token"), str) or not token["access_token"]:
            app.logger.error("SolarEdge-Token-Antwort enthält kein Access-Token.")
            return render_template_string(PAGE, message="Die Antwort von SolarEdge enthält kein Access-Token."), 502
        site_id = request.args.get("site_id")
        if site_id:
            token["site_id"] = site_id
        return render_template_string(PAGE, message="Anmeldung erfolgreich.", token=json.dumps(token, indent=2))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
