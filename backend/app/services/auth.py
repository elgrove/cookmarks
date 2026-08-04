"""Password hashing and browser sessions — the only module that knows how a password
or a session token is stored. Both use the standard library: scrypt for passwords,
`secrets` for tokens, stored SHA-256'd so a leaked database hands over no live session.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserSession

COOKIE_NAME = "cm_session"
SESSION_TTL = timedelta(days=30)

# scrypt cost parameters — n=2**14 keeps a login well under 100ms on the home server.
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16

# A hash no password can ever produce, for the implicit user of auth_mode="none".
UNUSABLE_PASSWORD = "!"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p)


def hash_password(password: str) -> str:
    """`scrypt$n$r$p$<salt-b64>$<hash-b64>` — self-describing, so the parameters can be
    raised later without invalidating existing hashes."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    candidate = _derive(password, salt, int(n), int(r), int(p))
    return hmac.compare_digest(candidate, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user: User) -> str:
    """Start a session for `user` and return the raw cookie token (never stored)."""
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    session.commit()
    return token


def resolve_session(session: Session, token: str) -> User | None:
    """The user behind a cookie token, or None if it is unknown or expired. An expired
    row is deleted on the way past, so stale sessions do not accumulate."""
    row = session.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if row is None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        session.delete(row)
        session.commit()
        return None
    return session.get(User, row.user_id)


def delete_session(session: Session, token: str) -> None:
    row = session.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if row is not None:
        session.delete(row)
        session.commit()


def implicit_user(session: Session) -> User:
    """The single user every request resolves to under auth_mode="none": the oldest
    account, or a freshly created `default` admin on an empty table. Personal state is
    still keyed to it, so switching such a deployment to "session" loses nothing."""
    user = session.scalar(select(User).order_by(User.created_at).limit(1))
    if user is None:
        user = User(username="default", password_hash=UNUSABLE_PASSWORD, is_admin=True)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
