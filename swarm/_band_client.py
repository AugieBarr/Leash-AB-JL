"""Shared Band REST client construction.

The ``AsyncRestClient`` must point at the configured REST URL — the SDK default
is a dev URL — so both the room seeder and the Band-side kill-switch build their
clients the same way. Keeping it here makes a URL/env-var change one edit, not
two. Importing this pulls in the Band SDK, so only the Band-touching modules
(``seed``, ``kill_switch``) use it; the offline governance path stays SDK-free.
"""
from __future__ import annotations

import os

from band.client.rest import AsyncRestClient


def rest_base_url() -> str:
    return os.getenv("THENVOI_REST_URL", "https://app.band.ai/").rstrip("/")


def band_client(api_key: str) -> AsyncRestClient:
    return AsyncRestClient(base_url=rest_base_url(), api_key=api_key)
