"""Account self-service for every role: email verification, forgotten password,
change password. Mounted under /auth next to sign-in."""
from __future__ import annotations

import secrets
from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from .. import mailer
from .. import models as M
from ..config import settings
from ..db import get_db
from ..ratelimit import client_ip, hit
from ..security import audit, current_user, hash_password, issue_refresh_token, make_access_token, now, \
    sha256_hex, verify_password

router = APIRouter(prefix="/auth", tags=["account"])

TTL = {"reset": timedelta(minutes=30), "verify": timedelta(days=7)}


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetIn(TokenIn):
    password: str = Field(min_length=10, max_length=128)


class ChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


def _issue(db: Session, user: M.User, purpose: str) -> str:
    # One live link per purpose: older unused links stop working.
    db.query(M.AuthToken).filter_by(user_id=user.id, purpose=purpose, used_at=None).update({"used_at": now()})
    raw = secrets.token_urlsafe(32)
    db.add(M.AuthToken(user_id=user.id, purpose=purpose, token_hash=sha256_hex(raw),
                       expires_at=now() + TTL[purpose]))
    return raw


def _redeem(db: Session, raw: str, purpose: str) -> M.User:
    row = db.query(M.AuthToken).filter_by(token_hash=sha256_hex(raw), purpose=purpose).one_or_none()
    if row is None or row.used_at is not None:
        raise HTTPException(400, "this link is invalid or was already used; request a new one")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if exp < now():
        raise HTTPException(400, "this link has expired; request a new one")
    user = db.get(M.User, row.user_id)
    if user is None or not user.active:
        raise HTTPException(400, "this link is invalid or was already used; request a new one")
    row.used_at = now()
    return user


def send_verification(db: Session, user: M.User, tasks: BackgroundTasks) -> None:
    raw = _issue(db, user, "verify")
    link = f"{settings.public_web_url}/#/verify/{raw}"
    tasks.add_task(mailer.send, user.email, "verify_email", "Confirm your DermaLens email",
                   f"Hello,\n\nPlease confirm this email address for your DermaLens account:\n{link}\n\n"
                   "The link works for 7 days.")


@router.post("/verify-email")
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    hit(f"verify:{client_ip(request)}", 20, 900)
    user = _redeem(db, body.token, "verify")
    if user.email_verified_at is None:
        user.email_verified_at = now()
    audit(db, user, "verify_email", "user", user.id, request)
    db.commit()
    return {"ok": True, "email": user.email}


@router.post("/resend-verification", status_code=202)
def resend_verification(tasks: BackgroundTasks, request: Request, user: M.User = Depends(current_user),
                        db: Session = Depends(get_db)):
    hit(f"resend:{user.id}", 3, 3600)
    if user.email_verified_at is None:
        send_verification(db, user, tasks)
        db.commit()
    return {"ok": True}


@router.post("/forgot-password", status_code=202)
def forgot_password(body: EmailIn, tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    """Always answers the same way, so it cannot be used to find out who has an account."""
    email = body.email.lower()
    hit(f"forgot-ip:{client_ip(request)}", 10, 900)
    hit(f"forgot:{email}", 3, 3600)
    user = db.query(M.User).filter_by(email=email).first()
    if user is not None and user.active:
        raw = _issue(db, user, "reset")
        link = f"{settings.public_web_url}/#/reset/{raw}"
        audit(db, None, "password_reset_requested", "user", user.id, request)
        db.commit()
        tasks.add_task(mailer.send, user.email, "password_reset", "Reset your DermaLens password",
                       f"Hello,\n\nSomeone asked to reset the password for this DermaLens account.\n"
                       f"To choose a new password, open:\n{link}\n\nThe link works for 30 minutes, once.")
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    hit(f"reset:{client_ip(request)}", 10, 900)
    user = _redeem(db, body.token, "reset")
    user.password_hash = hash_password(body.password)
    user.failed_logins, user.locked_until = 0, None
    if user.email_verified_at is None:  # they proved they read this inbox
        user.email_verified_at = now()
    db.query(M.RefreshToken).filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": now()})
    audit(db, user, "password_reset", "user", user.id, request)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(body: ChangeIn, request: Request, user: M.User = Depends(current_user),
                    db: Session = Depends(get_db)):
    hit(f"change:{user.id}", 5, 900)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "your current password is not correct")
    if body.current_password == body.new_password:
        raise HTTPException(400, "choose a password different from the current one")
    user.password_hash = hash_password(body.new_password)
    # Sign out every other device; this one gets fresh tokens.
    db.query(M.RefreshToken).filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": now()})
    audit(db, user, "change_password", "user", user.id, request)
    rt = issue_refresh_token(db, user)
    db.commit()
    return {"access_token": make_access_token(user), "refresh_token": rt, "role": user.role}
