"""Base class for data sources and shared source utilities."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from ..http import RateLimiter
from ..schema import CrisisEvent

logger = logging.getLogger(__name__)


class BaseSource:
    """Common configuration and rate-limiting for all event sources.

    Subclasses must set :attr:`name` and implement :meth:`fetch`.
    """

    name: str = "base"
    #: Default requests-per-second cap used when the config omits it.
    default_requests_per_second: float = 1.0

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = dict(config or {})
        self.rate_limiter = RateLimiter(
            float(self.config.get("requests_per_second", self.default_requests_per_second))
        )

    async def fetch(self, client: httpx.AsyncClient) -> List[CrisisEvent]:
        """Fetch and parse events from this source.

        Args:
            client: A shared ``httpx.AsyncClient`` owned by the pipeline.

        Returns:
            A list of normalized :class:`CrisisEvent` objects. An empty list
            signals "no data available" (as opposed to a raised exception).
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


def safe_float(value: Any, default: float = float("nan")) -> float:
    """Coerce a value to float, returning ``default`` on failure."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Coerce a value to int, returning ``default`` on failure."""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default