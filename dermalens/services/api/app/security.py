from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuditLog, RefreshToken, User

_ph = PasswordHasher()  # argon2id
_bearer = HTTPBearer(auto_error=False)
_fernet = Fernet(settings.data_key.encode())


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def encrypt(text: str | None) -> bytes | None:
    return None if text is None else _fernet.encrypt(text.encode())


def decrypt(blob: bytes | None) -> str | None:
    return None if blob is None else _fernet.decrypt(blob).decode()


def sha256_hex(s: str | bytes) -> str:
    return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_access_token(user: User) -> str:
    payload = {"sub": str(user.id), "role": user.role, "exp": now() + timedelta(minutes=settings.access_token_minutes),
               "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def issue_refresh_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user.id, token_hash=sha256_hex(raw),
                        expires_at=now() + timedelta(days=settings.refresh_token_days)))
    return raw


def rotate_refresh_token(db: Session, raw: str) -> User:
    row = db.query(RefreshToken).filter_by(token_hash=sha256_hex(raw)).one_or_none()
    if row is None:
        raise HTTPException(401, "invalid refresh token")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if row.revoked_at is not None:
        # Reuse of a rotated token: revoke every token for this user.
        db.query(RefreshToken).filter_by(user_id=row.user_id, revoked_at=None).update({"revoked_at": now()})
        db.commit()
        raise HTTPException(401, "refresh token reuse detected")
    if exp < now():
        raise HTTPException(401, "refresh token expired")
    row.revoked_at = now()
    user = db.get(User, row.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "account unavailable")
    return user


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    if payload.get("typ") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed for this role")
        return user
    return dep


def audit(db: Session, actor: User | None, action: str, entity: str, entity_id, request: Request | None = None,
          detail: dict | None = None) -> None:
    ip = request.client.host if request is not None and request.client else None
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity=entity, entity_id=str(entity_id),
                    ip_hash=sha256_hex(ip) if ip else None, detail=detail))


# ----- Signed upload URLs (dev stand-in for S3 pre-signed URLs) ---------------

def sign_upload(session_id: uuid.UUID, view: str, expires: datetime) -> str:
    body = f"{session_id}.{view}.{int(expires.timestamp())}"
    sig = hmac.new(settings.jwt_secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def verify_upload(token: str) -> tuple[uuid.UUID, str]:
    try:
        sid, view, exp, sig = token.split(".")
    except ValueError:
        raise HTTPException(403, "bad upload token")
    body = f"{sid}.{view}.{exp}"
    good = hmac.new(settings.jwt_secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        raise HTTPException(403, "bad upload signature")
    if int(exp) < int(now().timestamp()):
        raise HTTPException(403, "upload URL expired")
    return uuid.UUID(sid), view
