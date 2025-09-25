from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from database import db
from models import User, TokenData

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except JWTError:
        raise credentials_exception
    
    user_data = await db.get_user_profile(token_data.user_id)
    if user_data is None:
        raise credentials_exception
    
    # Convert to User model
    user = User(**user_data)
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def authenticate_user_credentials(email: str, password: str) -> Optional[User]:
    """Authenticate user with email and password"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔐 Starting authentication for: {email}")
    
    auth_result = await db.authenticate_user(email, password)
    logger.info(f"🔍 Supabase auth result: {auth_result}")
    
    if auth_result["success"]:
        logger.info(f"✅ Supabase auth successful for user ID: {auth_result['user'].id}")
        # Ensure a corresponding profile row exists or is updated
        ensured_profile = await db.ensure_user_profile(auth_result["user"])
        user_data = ensured_profile or await db.get_user_profile(auth_result["user"].id)
        logger.info(f"👤 User profile data: {user_data}")
        
        if user_data:
            logger.info(f"✅ Authentication complete for: {email}")
            return User(**user_data)
        else:
            logger.error(f"❌ No profile found for user ID: {auth_result['user'].id}")
    else:
        logger.warning(f"❌ Supabase auth failed: {auth_result.get('message', 'Unknown error')}")
    
    return None
