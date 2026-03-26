from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.auth.schema import AuthUserResponse, TokenResponse
from src.auth.service import login, refresh_tokens, signup
from src.database import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


def _build_token_response(
    access_token: str,
    access_expires_at,
    refresh_token: str,
    refresh_expires_at,
) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/signup", response_model=TokenResponse)
async def signup_user(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {str(key).strip(): value for key, value in form.items()}

    email = payload.get("email")
    password = payload.get("password")
    username = payload.get("username")

    if not email or not password:
        raise HTTPException(status_code=422, detail="email and password are required")

    access_token, access_expires_at, refresh_token, refresh_expires_at = signup(
        db=db,
        email=email,
        password=password,
        username=username,
    )
    return _build_token_response(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {str(key).strip(): value for key, value in form.items()}

    email = payload.get("email")
    password = payload.get("password")

    if not email or not password:
        raise HTTPException(status_code=422, detail="email and password are required")

    access_token, access_expires_at, refresh_token, refresh_expires_at = login(
        db=db,
        email=email,
        password=password,
    )
    return _build_token_response(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_user_tokens(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {str(key).strip(): value for key, value in form.items()}

    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=422, detail="refresh_token is required")

    access_token, access_expires_at, new_refresh_token, refresh_expires_at = refresh_tokens(
        db=db,
        refresh_token=refresh_token,
    )
    return _build_token_response(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=new_refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


@router.get("/me", response_model=AuthUserResponse)
def current_user(user=Depends(get_current_user)):
    return AuthUserResponse.model_validate(user)
