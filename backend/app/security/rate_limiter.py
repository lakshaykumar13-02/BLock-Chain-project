import os
import time
import threading
from collections import defaultdict
from fastapi import HTTPException, status

class LoginRateLimiter:
    """
    Thread-safe in-memory rate limiter for login attempts.
    Protects against credential stuffing and brute-force attacks by tracking
    failed authentication attempts per key (IP address and/or username).
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _clean_old_attempts(self, key: str, now: float) -> list[float]:
        cutoff = now - self.window_seconds
        valid = [t for t in self._failures[key] if t > cutoff]
        self._failures[key] = valid
        return valid

    def check_rate_limit(self, key: str) -> None:
        """
        Check if the key has exceeded the maximum allowed failed attempts.
        Raises HTTP 429 Too Many Requests with Retry-After header if blocked.
        """
        now = time.time()
        with self._lock:
            attempts = self._clean_old_attempts(key, now)
            if len(attempts) >= self.max_attempts:
                oldest_relevant = attempts[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest_relevant)) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts. Please wait before retrying.",
                    headers={"Retry-After": str(retry_after)}
                )

    def record_failure(self, key: str) -> None:
        """Record a failed authentication attempt."""
        now = time.time()
        with self._lock:
            self._clean_old_attempts(key, now)
            self._failures[key].append(now)

    def record_success(self, key: str) -> None:
        """Clear failed attempts upon successful authentication."""
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        """Reset all rate limiter state (used in testing)."""
        with self._lock:
            self._failures.clear()

# Global login rate limiter instance (5 failed attempts per 60 seconds)
login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)

def get_client_ip(request, trusted_proxies_str: str | None = None) -> str:
    """
    Safely extract client IP address to prevent rate limit spoofing.
    X-Forwarded-For is ONLY trusted if the direct peer IP (request.client.host)
    is explicitly listed in TRUSTED_PROXIES (defaulting to '127.0.0.1,::1').
    If the direct peer is not trusted, X-Forwarded-For is strictly ignored.
    """
    peer_ip = request.client.host if (request and request.client) else "127.0.0.1"

    if trusted_proxies_str is None:
        trusted_proxies_str = os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1")

    trusted_proxies = {p.strip() for p in trusted_proxies_str.split(",") if p.strip()}

    if peer_ip in trusted_proxies and request and hasattr(request, "headers"):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            first_ip = forwarded.split(",")[0].strip()
            if first_ip:
                return first_ip

    return peer_ip

