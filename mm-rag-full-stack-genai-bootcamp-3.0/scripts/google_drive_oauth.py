from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from backend.app.connectors.google_oauth import (
    GOOGLE_DRIVE_READONLY_SCOPE,
    GOOGLE_TOKEN_ENDPOINT,
    GoogleOAuthClientConfig,
    GoogleOAuthCredentialError,
    save_google_token,
)

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_PATH = Path("data/runtime/credentials/google-drive-token.json")


class _Callback:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.query: dict[str, list[str]] | None = None


def authorization_url(*, client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{
        urlencode(
            {
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': GOOGLE_DRIVE_READONLY_SCOPE,
                'access_type': 'offline',
                'prompt': 'consent',
                'include_granted_scopes': 'true',
                'state': state,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
            }
        )
    }"


def exchange_code(
    *,
    client: httpx.Client,
    config: GoogleOAuthClientConfig,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    try:
        response = client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret.get_secret_value(),
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleOAuthCredentialError("Google OAuth authorization failed") from exc
    if not isinstance(payload, dict):
        raise GoogleOAuthCredentialError("Google OAuth returned an invalid response")
    return payload


def authorize(client_config_path: Path, token_path: Path, timeout_seconds: int) -> None:
    config = GoogleOAuthClientConfig.load(client_config_path)
    callback = _Callback()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/oauth2callback":
                self.send_error(404)
                return
            callback.query = parse_qs(parsed.query)
            callback.event.set()
            body = b"Google Drive authorization received. You may close this tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth2callback"
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    url = authorization_url(
        client_id=config.client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print("Opening Google authorization in your default browser.")
        if not webbrowser.open(url):
            print("Open this URL in a regular browser:")
            print(url)
        if not callback.event.wait(timeout_seconds):
            raise GoogleOAuthCredentialError("Google OAuth authorization timed out")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    query = callback.query or {}
    if query.get("state", [""])[0] != state:
        raise GoogleOAuthCredentialError("Google OAuth state validation failed")
    if query.get("error"):
        raise GoogleOAuthCredentialError("Google OAuth authorization was denied")
    code = query.get("code", [""])[0]
    if not code:
        raise GoogleOAuthCredentialError("Google OAuth did not return an authorization code")
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        payload = exchange_code(
            client=client,
            config=config,
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
        )
    save_google_token(token_path.resolve().as_uri(), payload)
    print(f"Google Drive credential stored securely at {token_path.resolve()}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorize the private MM-RAG Google Drive learning connector"
    )
    parser.add_argument("--client-config", type=Path, required=True)
    parser.add_argument("--token-path", type=Path, default=DEFAULT_TOKEN_PATH)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.timeout_seconds < 30 or args.timeout_seconds > 900:
        raise SystemExit("--timeout-seconds must be between 30 and 900")
    try:
        authorize(args.client_config, args.token_path, args.timeout_seconds)
    except GoogleOAuthCredentialError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
