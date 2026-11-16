from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models as M
from ..config import settings
from ..db import get_db
from ..schemas import LoginIn, RefreshIn, RegisterIn, TokensOut
from ..security import audit, current_user, hash_password, issue_refresh_token, make_access_token, rotate_refresh_token, \
    verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(db: Session, user: M.User) -> TokensOut:
    rt = issue_refresh_token(db, user)
    db.commit()
    return TokensOut(access_token=make_access_token(user), refresh_token=rt, role=user.role)


@router.post("/register", response_model=TokensOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
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
    return _tokens(db, user)


@router.post("/login", response_model=TokensOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(M.User).filter_by(email=body.email.lower()).first()
    if user is None or user.deleted_at is not None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "wrong email or password")
    if user.disabled_at is not None:
        raise HTTPException(403, "this account is disabled; contact your DermaLens admin")
    audit(db, user, "login", "user", user.id, request)
    return _tokens(db, user)


@router.post("/refresh", response_model=TokensOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    user = rotate_refresh_token(db, body.refresh_token)
    return _tokens(db, user)


@router.get("/me")
def me(user: M.User = Depends(current_user)):
    """Who is signed in; the app opens the home screen for this role."""
    return {"id": str(user.id), "email": user.email, "role": user.role, "display_name": user.display_name}
