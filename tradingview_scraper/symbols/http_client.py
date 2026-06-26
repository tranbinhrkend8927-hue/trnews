"""Shared HTTP client for TradingView scraper modules."""

from typing import Mapping, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TradingViewHttpClient:
    """Small wrapper around requests.Session with shared timeout and retries."""

    def __init__(
        self,
        headers: Optional[Mapping[str, str]] = None,
        timeout: float = 10,
        retries: int = 2,
        session: Optional[requests.Session] = None,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.headers = dict(headers or {})

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=0.2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(self, method: str, url: str, **kwargs):
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}) or {})
        timeout = kwargs.pop("timeout", self.timeout)
        return self.session.request(method, url, headers=headers, timeout=timeout, **kwargs)

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        self.session.close()
