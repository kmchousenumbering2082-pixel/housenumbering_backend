import base64
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.auth.schema import AuthUserResponse, TokenResponse
from src.auth.service import login, refresh_tokens, signup
from src.database import get_db
from src.users.models import User

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

    access_token, access_expires_at, new_refresh_token, refresh_expires_at = (
        refresh_tokens(
            db=db,
            refresh_token=refresh_token,
        )
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


@router.post("/delete")
def delete_user(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Soft delete the current user account."""
    user.is_deleted = True
    db.commit()
    return {"message": "User account has been deleted successfully"}


@router.get("/email-activate/{uid}/{token}")
def activate_email(uid: str, token: str, db: Session = Depends(get_db)):
    """Activate user email via activation link from email."""
    try:
        # Decode uid (base64)
        user_id = int(base64.b64decode(uid).decode())

        # Find user by id
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Mark email as verified
        user.mark_email_verified()
        db.commit()

        return {
            "message": "Email activated successfully! You can now login.",
            "email": user.email,
            "username": user.username,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid activation link")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Activation failed: {str(e)}")
