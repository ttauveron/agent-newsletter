"""Initial Gmail OAuth2 authentication.

Run once to generate the token file:
    docker compose run --rm -p 8888:8888 newsletter-engine python -m gmail.auth

If port 8888 is already busy:
    docker compose run --rm -e GMAIL_AUTH_PORT=8889 -p 8889:8889 \
        newsletter-engine python -m gmail.auth
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_DEFAULT_SECRET_PATH = "/app/config/client_secret.json"  # nosec B105
_DEFAULT_TOKEN_PATH = "/app/config/gmail_token.json"  # nosec B105
_DEFAULT_AUTH_PORT = 8888


def main() -> None:
    secret_path = Path(os.environ.get("GMAIL_CLIENT_SECRET_PATH", _DEFAULT_SECRET_PATH))
    token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", _DEFAULT_TOKEN_PATH))
    auth_port = int(os.environ.get("GMAIL_AUTH_PORT", str(_DEFAULT_AUTH_PORT)))

    if not secret_path.exists():
        raise FileNotFoundError(f"Gmail OAuth client secret not found: {secret_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes=SCOPES)
    _validate_redirect_uri(flow.client_config)

    creds = flow.run_local_server(
        host="localhost",
        # Needed because the callback listener runs inside Docker.
        bind_addr="0.0.0.0",  # nosec B104
        port=auth_port,
        open_browser=False,
        redirect_uri_trailing_slash=False,
        authorization_prompt_message=(
            "\nOuvre cette URL dans ton navigateur :\n\n  {url}\n\n"
            "Après autorisation, Google doit afficher une page de succès.\n"
        ),
    )

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"\nToken sauvegardé dans {token_path}")


def _validate_redirect_uri(client_config: dict) -> None:
    redirect_uris = client_config.get("redirect_uris", [])
    has_loopback = any(uri.startswith("http://localhost") for uri in redirect_uris)
    if not has_loopback:
        raise ValueError(
            "Le client OAuth doit autoriser un redirect URI localhost. "
            f"Redirect URIs déclarées: {redirect_uris}"
        )


if __name__ == "__main__":
    main()
