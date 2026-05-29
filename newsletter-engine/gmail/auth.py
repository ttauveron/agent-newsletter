"""Initial Gmail OAuth2 authentication.

Run once to generate the token file:
    docker compose run --rm newsletter-engine python -m gmail.auth
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main() -> None:
    client_id = os.environ["GMAIL_CLIENT_ID"]
    client_secret = os.environ["GMAIL_CLIENT_SECRET"]
    token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", "/app/config/gmail_token.json"))

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",  # nosec B105
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # run_console prints a URL; paste the returned code into the terminal
    creds = flow.run_console()

    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"Token saved to {token_path}")


if __name__ == "__main__":
    main()
