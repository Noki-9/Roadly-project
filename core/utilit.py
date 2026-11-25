import ipaddress
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_REQUESTS = 6
request_log: dict[str, deque[float]] = defaultdict(deque)

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------
def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    candidate = forwarded.split(",")[0].strip() if forwarded else ""
    if not candidate and request.client:
        candidate = request.client.host
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return candidate or "unknown"


def check_rate_limit(
    key: str,
    limit: int = RATE_LIMIT_REQUESTS,
    window: float = RATE_LIMIT_WINDOW,
) -> None:
    now = time.monotonic()
    bucket = request_log[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = int(window - (now - bucket[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много запросов. Попробуйте снова через {retry_after} сек.",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)

