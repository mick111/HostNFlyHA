from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp


class HostNFlyApiError(Exception):
    """Generic API error."""


class HostNFlyAuthError(HostNFlyApiError):
    """Authentication error."""


@dataclass
class HostNFlyTokens:
    access_token: str
    client: str
    uid: str


class HostNFlyApi:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        email: str,
        password: str | None = None,
        tokens: HostNFlyTokens | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._host = self._normalize_host(host)
        self._tokens: HostNFlyTokens | None = tokens

    @property
    def host(self) -> str:
        return self._host

    @property
    def tokens(self) -> HostNFlyTokens | None:
        return self._tokens

    def _normalize_host(self, host: str) -> str:
        if not host.startswith("http"):
            host = f"https://{host}"
        return host.rstrip("/")

    def _base_headers(self) -> dict[str, str]:
        parsed = urlparse(self._host)
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15"
            ),
            "Referer": "https://www.hostnfly.com/",
            "Origin": "https://www.hostnfly.com",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Host": parsed.netloc,
        }

    def _auth_headers(self) -> dict[str, str]:
        if not self._tokens:
            return {}
        return {
            "access-token": self._tokens.access_token,
            "client": self._tokens.client,
            "uid": self._tokens.uid,
        }

    async def async_login(self) -> None:
        if not self._password:
            raise HostNFlyAuthError("Missing credentials")
        url = f"{self._host}/api/v1/auth/sign_in"
        payload = {
            "email": self._email,
            "password": self._password,
            "terms_accepted": False,
            "from": "",
        }
        async with self._session.post(url, json=payload, headers=self._base_headers()) as resp:
            if resp.status != 200:
                raise HostNFlyAuthError(f"Authentication failed: {resp.status}")
            access_token = resp.headers.get("access-token")
            client = resp.headers.get("client")
            uid = resp.headers.get("uid")
            if not access_token or not client or not uid:
                raise HostNFlyAuthError("Missing auth headers")
            self._tokens = HostNFlyTokens(access_token=access_token, client=client, uid=uid)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        retry_on_auth: bool = True,
    ) -> dict[str, Any]:
        if not self._tokens:
            if self._password:
                await self.async_login()
            else:
                raise HostNFlyAuthError("Missing tokens")
        url = f"{self._host}{path}"
        headers = {**self._base_headers(), **self._auth_headers()}
        async with self._session.request(method, url, params=params, headers=headers) as resp:
            if resp.status in (401, 403) and retry_on_auth:
                if self._password:
                    await self.async_login()
                    return await self._request(method, path, params=params, retry_on_auth=False)
                raise HostNFlyAuthError(f"Authentication failed: {resp.status}")
            if resp.status != 200:
                raise HostNFlyApiError(f"API error: {resp.status}")
            return await resp.json()

    async def async_get_listings(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/listings")
        return data.get("listings", [])

    async def async_get_reservations(self, min_date: str, max_date: str) -> list[dict[str, Any]]:
        params = {
            "min_date": min_date,
            "max_date": max_date,
            "per_page": -1,
        }
        data = await self._request("GET", "/api/v2/reservations", params=params)
        return data.get("reservations", [])
