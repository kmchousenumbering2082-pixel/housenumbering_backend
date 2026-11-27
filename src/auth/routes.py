import base64
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.auth.schema import AuthUserResponse, TokenResponse
from src.auth.service import login, refresh_tokens, signup
from src.database import get_db
from src.users.models import User
from src.users.service import hash_password, verify_password
from src.utils.email import send_forgot_password_email

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


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


@router.get("/email_activate/{uid}/{token}")
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


@router.post("/forgot_password")
async def forgot_password(request: Request, db: Session = Depends(get_db)):
    """Send password reset email to user."""
    form = await request.form()
    email = form.get("email", "").strip().lower()

    if not email:
        raise HTTPException(status_code=422, detail="email is required")

    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Don't reveal if email exists or not for security
        return {"message": "If email exists, password reset link has been sent"}

    # Generate reset token
    try:
        uid = base64.b64encode(str(user.id).encode()).decode()
        token = base64.b64encode(f"{user.id}:{user.email}".encode()).decode()
        user_name = user.username or user.email.split("@")[0]

        email_sent = send_forgot_password_email(
            user_email=user.email,
            user_name=user_name,
            uid=uid,
            token=token,
        )

        if email_sent:
            print(f"Password reset email sent to {user.email}")
        else:
            print(f"Failed to send password reset email to {user.email}")

    except Exception as e:
        print(f"Error sending password reset email: {str(e)}")

    return {"message": "If email exists, password reset link has been sent"}


@router.get("/reset_password/{uid}/{token}", response_class=HTMLResponse)
async def show_reset_password_form(uid: str, token: str, db: Session = Depends(get_db)):
    """Show password reset form."""
    try:
        # Validate uid/token by checking if user exists
        user_id = int(base64.b64decode(uid).decode())
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Read the HTML template
        template_path = "src/users/templates/forgot_password_confirm.html"
        with open(template_path, "r") as f:
            html_content = f.read()

        return html_content

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid reset link")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")


@router.post("/reset_password/{uid}/{token}")
async def reset_password(
    uid: str, token: str, request: Request, db: Session = Depends(get_db)
):
    """Reset user password using reset token from email."""
    form = await request.form()
    new_password = form.get("new_password", "").strip()
    confirm_password = form.get("confirm_password", "").strip()

    # Validate passwords
    if not new_password:
        raise HTTPException(status_code=422, detail="password is required")

    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="passwords do not match")

    if len(new_password) < 6:
        raise HTTPException(
            status_code=422, detail="password must be at least 6 characters"
        )

    try:
        # Decode uid (base64)
        user_id = int(base64.b64decode(uid).decode())

        # Find user by id
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update password
        user.password = hash_password(new_password)
        db.commit()

        return {
            "message": "Password reset successfully! You can now login with your new password.",
            "email": user.email,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid password reset link")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Password reset failed: {str(e)}")


@router.post("/change_password")
async def change_password(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password for authenticated user."""
    form = await request.form()
    old_password = form.get("old_password", "").strip()
    new_password = form.get("new_password", "").strip()
    confirm_password = form.get("confirm_password", "").strip()

    # Validate inputs
    if not old_password:
        raise HTTPException(status_code=422, detail="old_password is required")

    if not new_password:
        raise HTTPException(status_code=422, detail="new_password is required")

    if new_password != confirm_password:
        raise HTTPException(status_code=422, detail="passwords do not match")

    if len(new_password) < 6:
        raise HTTPException(
            status_code=422, detail="password must be at least 6 characters"
        )

    # Verify old password is correct
    if not verify_password(old_password, user.password):
        raise HTTPException(status_code=401, detail="old password is incorrect")

    try:
        # Update password
        user.password = hash_password(new_password)
        db.commit()

        return {
            "message": "Password changed successfully!",
            "email": user.email,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Password change failed: {str(e)}")
