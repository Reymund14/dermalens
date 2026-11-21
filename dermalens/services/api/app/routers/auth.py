from datetime import timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import get_db
from ..ratelimit import enforce, hit
from ..schemas import LoginIn, RefreshIn, RegisterIn, TokensOut
from ..security import audit, current_user, hash_password, issue_refresh_token, make_access_token, now, \
    rotate_refresh_token, verify_password
from .account import send_verification

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _tokens(db: Session, user: M.User) -> TokensOut:
    rt = issue_refresh_token(db, user)
    db.commit()
    return TokensOut(access_token=make_access_token(user), refresh_token=rt, role=user.role)


@router.post("/register", response_model=TokensOut, status_code=201)
def register(body: RegisterIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    hit(f"register:{_ip(request)}", 20, 3600)
    if not body.accepted_boundary:
        raise HTTPException(422, "the informational-use statement must be accepted")
    email = body.email.lower()
    if db.query(M.User).filter_by(email=email).first():
        raise HTTPException(409, "an account with this email already exists")
    user = M.User(email=email, password_hash=hash_password(body.password), role="patient")
    db.add(user)
    db.flush()
    # Service consent is required to create an account; everything else is opt-in later.
    db.add(M.Consent(user_id=user.id, purpose="service", policy_version=settings.policy_version, granted=True))
    audit(db, user, "register", "user", user.id, request)
    send_verification(db, user, tasks)
    return _tokens(db, user)


@router.post("/login", response_model=TokensOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    hit(f"login-ip:{_ip(request)}", 30, 300)
    hit(f"login:{body.email.lower()}", 10, 300)
    email = body.email.lower()
    user = db.query(M.User).filter_by(email=email).first()
    if user is not None and user.locked_until is not None:
        until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
        if until > now():
            mins = max(1, int((until - now()).total_seconds() // 60) + 1)
            raise HTTPException(423, f"too many wrong passwords; this account is locked for {mins} more "
                                     "minute(s). You can also reset your password.")
    if user is None or user.deleted_at is not None or not verify_password(body.password, user.password_hash):
        if user is not None and user.deleted_at is None:
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= settings.max_failed_logins:
                user.failed_logins, user.locked_until = 0, now() + timedelta(minutes=settings.lockout_minutes)
                audit(db, None, "account_locked", "user", user.id, request)
            db.commit()
        raise HTTPException(401, "wrong email or password")
    if user.disabled_at is not None:
        raise HTTPException(403, "this account is disabled; contact your DermaLens admin")
    user.failed_logins, user.locked_until = 0, None
    audit(db, user, "login", "user", user.id, request)
    return _tokens(db, user)


@router.post("/refresh", response_model=TokensOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    enforce(f"refresh:{_ip(request)}", limit=60, window_seconds=300)
    user = rotate_refresh_token(db, body.refresh_token)
    return _tokens(db, user)


@router.get("/me")
def me(user: M.User = Depends(current_user)):
    """Who is signed in; the app opens the home screen for this role."""
    return {"id": str(user.id), "email": user.email, "role": user.role, "display_name": user.display_name,
            "email_verified": user.email_verified_at is not None}
