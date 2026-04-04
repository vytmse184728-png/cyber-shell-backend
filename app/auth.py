from __future__ import annotations

import hmac

from flask import current_app



def is_valid_bearer_header(header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = f"Bearer {current_app.config['API_KEY']}"
    return hmac.compare_digest(header_value, expected)
