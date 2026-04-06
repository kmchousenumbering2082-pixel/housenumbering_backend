import secrets
import base64
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from src.users.models import UserAuthToken, AuthTokenPurpose


def generate_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def encode_uid_b64(user_id: int) -> str:
    """Encode user ID to base64 string."""
    return base64.b64encode(str(user_id).encode()).decode()


def decode_uid_b64(encoded_uid: str) -> int | None:
    """Decode base64 encoded user ID. Returns None if invalid."""
    try:
        return int(base64.b64decode(encoded_uid).decode())
    except Exception:
        return None


def create_auth_token(
    db: Session,
    user_id: int,
    purpose: AuthTokenPurpose,
    expires_in_hours: int = 24,
) -> tuple[str, str]:
    """
    Create a new authentication token for a user.
    
    Args:
        db: Database session
        user_id: User ID
        purpose: Token purpose (activate_account or reset_password)
        expires_in_hours: Token expiration time in hours
    
    Returns:
        Tuple of (raw_token, token_hash)
    """
    raw_token = generate_token()
    token_hash = UserAuthToken.hash_token(raw_token)
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=expires_in_hours)

    auth_token = UserAuthToken(
        user_id=user_id,
        purpose=purpose,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(auth_token)
    db.commit()

    return raw_token, token_hash


def validate_auth_token(
    db: Session,
    user_id: int,
    token: str,
    purpose: AuthTokenPurpose,
) -> bool:
    """
    Validate an authentication token.
    
    Args:
        db: Database session
        user_id: User ID
        token: Raw token string
        purpose: Expected token purpose
    
    Returns:
        True if token is valid, False otherwise
    """
    token_hash = UserAuthToken.hash_token(token)
    auth_token = db.query(UserAuthToken).filter(
        UserAuthToken.user_id == user_id,
        UserAuthToken.token_hash == token_hash,
        UserAuthToken.purpose == purpose,
        UserAuthToken.consumed_at.is_(None),  # Token not yet used
        UserAuthToken.expires_at > datetime.now(UTC).replace(tzinfo=None),  # Token not expired
    ).first()

    return auth_token is not None


def consume_auth_token(
    db: Session,
    user_id: int,
    token: str,
    purpose: AuthTokenPurpose,
) -> bool:
    """
    Mark an authentication token as consumed.
    
    Args:
        db: Database session
        user_id: User ID
        token: Raw token string
        purpose: Expected token purpose
    
    Returns:
        True if token was successfully consumed, False otherwise
    """
    token_hash = UserAuthToken.hash_token(token)
    auth_token = db.query(UserAuthToken).filter(
        UserAuthToken.user_id == user_id,
        UserAuthToken.token_hash == token_hash,
        UserAuthToken.purpose == purpose,
        UserAuthToken.consumed_at.is_(None),
        UserAuthToken.expires_at > datetime.now(UTC).replace(tzinfo=None),
    ).first()

    if not auth_token:
        return False

    auth_token.consumed_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(auth_token)
    db.commit()
    return True
