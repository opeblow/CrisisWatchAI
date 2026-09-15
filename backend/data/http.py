"""Shared asynchronous HTTP utilities: retries, timeouts and per-source rate limiting."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, Iterable, Optional, Union

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 1.0
DEFAULT_FILE_SIZE_LIMIT = 20 * 1024 * 1024  # 20 MiB safety cap for downloads

#: Status codes considered transient and therefore retryable.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

DEFAULT_HEADERS = {"User-Agent": "CrisisWatchAI/1.0 data-ingestion (+research)"}


class RateLimiter:
    """Enforces a minimum interval between requests (spacing based limiter).

    This is a conservative per-source throttle: each :meth:`acquire` call blocks
    until at least ``1 / calls_per_second`` seconds have passed since the last
    release. Safe to share across concurrent tasks.
    """

    def __init__(self, calls_per_second: float = 1.0) -> None:
        self._interval = 1.0 / calls_per_second if calls_per_second > 0 else 0.0
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


def _parse_retry_after(value: Optional[str]) -> float:
    """Convert a ``Retry-After`` header into seconds (HTTP-date unsupported)."""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    json: Any = None,
    content: Optional[bytes] = None,
    rate_limiter: Optional[RateLimiter] = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """Perform an HTTP request with exponential backoff retries and optional
    per-source rate limiting.

    Raises:
        httpx.HTTPError: The final (non-retryable) error or last retry failure.
    """
    for attempt in range(retries + 1):
        if rate_limiter is not None:
            await rate_limiter.acquire()

        try:
            response = await client.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json,
                content=content,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            if attempt >= retries:
                logger.warning(
                    "HTTP error on %s %s after %d attempts: %s",
                    method, url, attempt + 1, exc,
                )
                raise
            delay = backoff * (2**attempt) + random.uniform(0, 0.5)
            logger.info(
                "Transient failure %s %s (attempt %d/%d), retrying in %.2fs: %s",
                method, url, attempt + 1, retries + 1, delay, exc,
            )
            await asyncio.sleep(delay)
            continue

        if response.status_code in RETRYABLE_STATUSES:
            if attempt >= retries:
                response.raise_for_status()  # guaranteed to raise
                raise httpx.HTTPError(f"Exhausted retries for {url}")
            wait = max(
                backoff * (2**attempt) + random.uniform(0, 0.5),
                _parse_retry_after(response.headers.get("Retry-After")),
            )
            logger.info(
                "HTTP %d on %s (attempt %d/%d), retrying in %.2fs",
                response.status_code, url, attempt + 1, retries + 1, wait,
            )
            await asyncio.sleep(wait)
            continue

        response.raise_for_status()  # raises on other 4xx/5xx immediately
        return response

    raise httpx.HTTPError(f"Exhausted retries for {url}")  # pragma: no cover


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    **kwargs: Any,
) -> str:
    """Fetch a URL and return its decoded text body."""
    response = await request_with_retry(client, "GET", url, **kwargs)
    return response.text


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    **kwargs: Any,
) -> Any:
    """Fetch a URL and return its parsed JSON payload."""
    response = await request_with_retry(client, "GET", url, **kwargs)
    return response.json()


async def fetch_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_size: int = DEFAULT_FILE_SIZE_LIMIT,
    **kwargs: Any,
) -> bytes:
    """Fetch a URL and return the raw bytes (bounded by ``max_size``)."""
    headers = {**DEFAULT_HEADERS, **(kwargs.pop("headers", None) or {})}
    response = await request_with_retry(
        client, "GET", url, headers=headers, **kwargs,
    )
    body = response.content
    if len(body) > max_size:
        raise ValueError(f"Download exceeds size limit ({len(body)} > {max_size})")
    return body