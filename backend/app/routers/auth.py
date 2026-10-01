from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.database import get_db
from app.dependencies import current_user
from app.models import RefreshSession, User
from app.schemas import LoginInput, LoginOutput, UserView
from app.security import hash_token_id, make_token, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)
REFRESH_COOKIE = "hotel_refresh"


def create_session(db: Session, user: User, response: Response) -> str:
    refresh_lifetime = timedelta(days=settings.refresh_token_days)
    refresh_token, token_id, expires_at = make_token(user.id, "refresh", refresh_lifetime)
    db.add(RefreshSession(user_id=user.id, token_hash=hash_token_id(token_id), expires_at=expires_at))
    access_token, _, _ = make_token(user.id, "access", timedelta(minutes=settings.access_token_minutes))
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=int(refresh_lifetime.total_seconds()),
        path="/api/v1/auth",
    )
    return access_token


@router.post("/login", response_model=LoginOutput)
@limiter.limit("8/minute")
def login(request: Request, payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> LoginOutput:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    access_token = create_session(db, user, response)
    db.commit()
    return LoginOutput(access_token=access_token, user=user)


@router.post("/refresh", response_model=LoginOutput)
@limiter.limit("20/minute")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOutput:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session required")
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "type", "jti"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh session") from exc
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh session")
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_token_id(claims["jti"]))
    )
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has expired")
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has expired")
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active or user.id != session.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh session")
    session.revoked_at = now
    access_token = create_session(db, user, response)
    db.commit()
    return LoginOutput(access_token=access_token, user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except jwt.InvalidTokenError:
            claims = {}
        token_id = claims.get("jti")
        if token_id:
            session = db.scalar(
                select(RefreshSession).where(RefreshSession.token_hash == hash_token_id(token_id))
            )
            if session and session.revoked_at is None:
                session.revoked_at = datetime.now(timezone.utc)
                db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth", secure=settings.cookie_secure, httponly=True, samesite="strict")
    return response


@router.get("/me", response_model=UserView)
def me(user: User = Depends(current_user)) -> User:
    return user