#!/usr/bin/env python3
"""Export WHOOP data (sleep, recovery, workouts, cycles) to CSV files."""

import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv

# ── Configuration ──────────────────────────────────────────────────────────────

load_dotenv("whoop.env")

CLIENT_ID = os.getenv("WHOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:3000/callback"

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer"

SCOPES = "read:recovery read:sleep read:workout read:cycles offline"
START_DATE = "2025-09-01T00:00:00.000Z"
END_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # seconds


# ── OAuth 2.0 ──────────────────────────────────────────────────────────────────

def get_auth_code() -> str:
    """Open browser for OAuth consent and capture the authorization code."""
    state = secrets.token_urlsafe(16)
    auth_code_holder: dict = {}
    server_error: dict = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)

            if params.get("state", [None])[0] != state:
                server_error["msg"] = "State mismatch – possible CSRF attack."
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Please try again.")
                return

            if "error" in params:
                server_error["msg"] = params["error"][0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"OAuth error: {params['error'][0]}".encode())
                return

            auth_code_holder["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this tab.</p></body></html>"
            )

        def log_message(self, format, *args):
            pass  # suppress request logs

    server = http.server.HTTPServer(("localhost", 3000), CallbackHandler)

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })
    url = f"{AUTH_URL}?{params}"

    print("Opening browser for WHOOP authorization...")
    webbrowser.open(url)

    # Wait for the callback (handle one request at a time until we get the code)
    while "code" not in auth_code_holder and "msg" not in server_error:
        server.handle_request()

    server.server_close()

    if "msg" in server_error:
        print(f"Authorization failed: {server_error['msg']}")
        sys.exit(1)

    print("Authorization code received.")
    return auth_code_holder["code"]


def exchange_token(auth_code: str) -> str:
    """Exchange authorization code for an access token."""
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    token_data = resp.json()
    print("Access token obtained.")
    return token_data["access_token"]


# ── API helpers ────────────────────────────────────────────────────────────────

def api_get(session: requests.Session, endpoint: str, params: dict) -> dict:
    """GET with exponential backoff on 429 / 5xx."""
    url = f"{API_BASE}{endpoint}"
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.get(url, params=params)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = backoff
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                wait = max(float(reset), wait)
            print(f"  Rate limited / server error ({resp.status_code}), "
                  f"retrying in {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
            backoff *= 2
        else:
            resp.raise_for_status()
    print(f"Failed after {MAX_RETRIES} retries for {endpoint}")
    sys.exit(1)


def fetch_all(session: requests.Session, endpoint: str, label: str) -> list[dict]:
    """Paginate through an endpoint and return all records."""
    all_records = []
    params = {"start": START_DATE, "end": END_DATE}
    while True:
        data = api_get(session, endpoint, params)
        records = data.get("records", [])
        all_records.extend(records)
        print(f"  Fetched {len(all_records)} {label} records so far...")
        next_token = data.get("next_token")
        if not next_token:
            break
        params["nextToken"] = next_token
    print(f"Fetched {len(all_records)} {label} records total.")
    return all_records


# ── Flatten & export ───────────────────────────────────────────────────────────

def flatten(record: dict, parent_key: str = "", sep: str = "_") -> dict:
    """Recursively flatten nested dicts into snake_case columns."""
    items = {}
    for k, v in record.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten(v, new_key, sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v)
        else:
            items[new_key] = v
    return items


def save_csv(records: list[dict], filename: str):
    """Flatten records and save to CSV."""
    if not records:
        print(f"No records for {filename}, skipping.")
        return
    flat = [flatten(r) for r in records]
    df = pd.DataFrame(flat)
    df.columns = [c.lower() for c in df.columns]
    df.to_csv(filename, index=False)
    print(f"Saved {len(df)} rows → {filename}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET in .env")
        sys.exit(1)

    # Authenticate
    auth_code = get_auth_code()
    access_token = exchange_token(auth_code)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {access_token}"})

    # Fetch data
    endpoints = [
        ("/v2/activity/sleep",   "sleep",    "sleep.csv"),
        ("/v2/recovery",         "recovery", "recovery.csv"),
        ("/v2/activity/workout", "workout",  "workouts.csv"),
        ("/v2/cycle",            "cycle",    "cycles.csv"),
    ]

    for endpoint, label, filename in endpoints:
        print(f"\n── {label.upper()} ──")
        records = fetch_all(session, endpoint, label)
        save_csv(records, filename)

    print("\nDone! All CSV files exported.")


if __name__ == "__main__":
    main()
