"""Read the response to the device code request, the first request of the login."""
from __future__ import annotations

import json
from typing import Any


# the fields of the response that `_AuthState._oauth_login` reads
CODE_FIELDS = ("device_code", "user_code", "interval", "verification_uri", "expires_in")


def read_json(body: bytes) -> Any:
    """Return the value of a JSON response body, or None when the body is not JSON."""
    try:
        return json.loads(body)
    except ValueError:
        return None


def device_code_error(status: int, body: Any) -> str | None:
    """Return None for a device code response with a code, else Twitch's message, or the status without one.

    body is the value that `read_json` returns for the response.
    """
    if status == 200 and isinstance(body, dict) and all(field in body for field in CODE_FIELDS):
        return None
    if isinstance(body, dict) and isinstance(body.get("message"), str) and body["message"]:
        return body["message"]
    return str(status)
