"""Small Patreon API v2 client for reading campaign posts."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import requests

BASE_URL = "https://www.patreon.com/api/oauth2/v2"
POST_FIELDS = "title,content,published_at,url"


@dataclass(frozen=True)
class PatreonPost:
    id: str
    title: str
    content: str
    published_at: str | None
    url: str | None


class PatreonApiError(RuntimeError):
    """An API response that prevents a complete audit."""


class PatreonClient:
    def __init__(self, token: str, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    def discover_campaigns(self) -> list[str]:
        """Return campaign IDs belonging to the authenticated creator."""
        url = f"{BASE_URL}/campaigns"
        campaigns: list[str] = []
        while url:
            try:
                response = self.session.get(url, timeout=30)
            except requests.RequestException:
                raise PatreonApiError("Could not connect to Patreon. Check your connection and try again.") from None
            if response.status_code == 401:
                raise PatreonApiError("Patreon rejected the token. Enter a valid creator access token.")
            if response.status_code == 403:
                raise PatreonApiError("Campaign discovery was denied. Check that your token has the campaigns permission.")
            if not response.ok:
                raise PatreonApiError(f"Campaign discovery failed (HTTP {response.status_code}). Try again later.")
            try:
                payload = response.json()
                items = payload["data"]
                if not isinstance(items, list):
                    raise ValueError
                for item in items:
                    campaign_id = str(item["id"])
                    if not campaign_id.isdigit():
                        raise ValueError
                    if campaign_id not in campaigns:
                        campaigns.append(campaign_id)
                url = payload.get("links", {}).get("next")
            except (ValueError, KeyError, TypeError, AttributeError):
                raise PatreonApiError("Patreon returned an invalid campaign response. Try again later.") from None
        if not campaigns:
            raise PatreonApiError("No creator campaign was found for this token. Use the access token for your creator account.")
        return campaigns

    def discover_campaign_id(self) -> str:
        campaigns = self.discover_campaigns()
        if len(campaigns) != 1:
            raise PatreonApiError("Multiple campaigns found. Choose one with --campaign-id: " + ", ".join(campaigns))
        return campaigns[0]

    def iter_campaign_posts(self, campaign_id: str) -> Iterator[PatreonPost]:
        """Yield every page, following the server-provided `links.next` URL."""
        url: str | None = f"{BASE_URL}/campaigns/{campaign_id}/posts"
        params: dict[str, Any] | None = {"fields[post]": POST_FIELDS, "page[count]": 100}
        while url:
            response = self.session.get(url, params=params, timeout=30)
            params = None  # `links.next` already contains its cursor and field parameters.
            if not response.ok:
                detail = response.text[:500]
                raise PatreonApiError(f"Patreon API returned HTTP {response.status_code}: {detail}")
            payload = response.json()
            for item in payload.get("data", []):
                attributes = item.get("attributes", {})
                yield PatreonPost(
                    id=str(item["id"]),
                    title=attributes.get("title") or "(untitled)",
                    content=attributes.get("content") or "",
                    published_at=attributes.get("published_at"),
                    url=attributes.get("url"),
                )
            url = payload.get("links", {}).get("next")
