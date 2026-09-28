"""Minimal cookie-based doctor authentication endpoints."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from api.deps.auth import COOKIE_NAME, get_current_doctor
from martin.auth.session_service import DoctorIdentity, SESSION_HOURS, SessionService


router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _public_doctor(doctor: DoctorIdentity) -> dict[str, str]:
    return {
        "id": doctor.id,
        "username": doctor.username,
        "display_name": doctor.display_name,
    }


@router.post("/login")
def login(credentials: LoginRequest, response: Response):
    result = SessionService().login(credentials.username, credentials.password)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, doctor = result
    secure = os.environ.get("MARTIN_COOKIE_SECURE", "false").lower() == "true"
    secure = secure or os.environ.get("MARTIN_ENV", "").lower() == "production"
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
        path="/api",
    )
    return _public_doctor(doctor)


@router.post("/logout")
def logout(request: Request, response: Response, doctor: DoctorIdentity = Depends(get_current_doctor)):
    SessionService().logout(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/api")
    return {"status": "logged_out"}


@router.get("/me")
def current_doctor(doctor: DoctorIdentity = Depends(get_current_doctor)):
    return _public_doctor(doctor)
