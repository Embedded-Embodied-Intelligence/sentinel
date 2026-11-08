"""Sessions, CSRF tokens and request limits of the web layer (ADR-0024).

A demo visitor's session id travels in a cookie signed with HMAC-SHA256 under the server's
secret key (`secret.key` in the data directory, created on first start, mode 0600), so a client
cannot forge or guess another session. Every state-changing request carries the session's CSRF
token in the `X-CSRF-Token` header (double submit: the token is also a cookie that the page's
script reads); the token is an HMAC of the session id, so a cross-site page can neither read nor
compute it. Requests are limited per client address with a token bucket; behind a local proxy
(Tailscale Funnel) the address comes from X-Forwarded-For, trusted only from this machine.
"""

import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

SESSION_COOKIE = "sentinel_session"
CSRF_COOKIE = "sentinel_csrf"
CSRF_HEADER = "X-CSRF-Token"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_local(address: str | None) -> bool:
    """Whether a TCP peer is this machine itself: a loopback address or one of its own, the
    source the routing table picks for that address. Some hosts rewrite the source of a
    connection to 127.0.0.1 to their main interface's address (WSL2 with Docker: the local
    proxy arrives as eth0's address), so 127.0.0.1 alone is not enough (WP16 hotfix)."""
    try:
        ip = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return True
    if ip.is_unspecified or ip.is_multicast:
        return False
    family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect((str(ip), 9))  # a datagram socket sends nothing on connect
            return bool(probe.getsockname()[0] == str(ip))
        except OSError:
            return False


def client_address(peer: str | None, forwarded: str | None, trust_proxy: bool) -> str:
    """The address a request is counted under (WP9c): its TCP peer, or, with `trust_proxy` and
    the local proxy (this machine, `is_local`) as the peer, the last X-Forwarded-For hop that is
    not this machine, the address the proxy saw (a client's own header comes before it). A
    header from any other peer is ignored, so a remote client cannot pick its address."""
    address = peer or "?"
    if not trust_proxy or not forwarded or not is_local(address):
        return address
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    outside = [hop for hop in hops if not is_local(hop)]
    return outside[-1] if outside else address


def load_key(path: Path) -> bytes:
    """The server's secret key, created (32 random bytes, mode 0600) if missing."""
    try:
        text = path.read_text(encoding="ascii").strip()
        if len(text) >= 64:
            return bytes.fromhex(text)
    except (OSError, ValueError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="ascii") as stream:
        stream.write(key.hex())
    return key


def _mac(key: bytes, purpose: str, value: str) -> str:
    return hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def calendar_token(key: bytes, project_id: str, nonce: str) -> str:
    """The secret of a project's calendar link (ADR-0035): derived from the app's key and the
    link's nonce, so the store never holds it and a new nonce revokes every old link."""
    return _mac(key, "calendar", f"{project_id}:{nonce}")[:32]


def calendar_valid(key: bytes, project_id: str, nonce: str | None, token: str) -> bool:
    if not nonce or not token:
        return False
    return hmac.compare_digest(token, calendar_token(key, project_id, nonce))


def sign(key: bytes, session_id: str) -> str:
    """The cookie value of a session id."""
    return f"{session_id}.{_mac(key, 'session', session_id)}"


def unsign(key: bytes, token: str | None) -> str | None:
    """The session id of a signed cookie value, None if it is missing or forged."""
    if not token or "." not in token:
        return None
    session_id, _, mac = token.rpartition(".")
    if not session_id or not hmac.compare_digest(mac, _mac(key, "session", session_id)):
        return None
    return session_id


def csrf_token(key: bytes, session_id: str) -> str:
    """The CSRF token of a session."""
    return _mac(key, "csrf", session_id)


def csrf_valid(key: bytes, session_id: str, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(str(token), csrf_token(key, session_id))


class RateLimiter:
    """At most `per_minute` requests per key and minute on average (token bucket, bursts up
    to `per_minute`)."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > 10_000:  # forget idle clients
                self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < 120}
            return True
