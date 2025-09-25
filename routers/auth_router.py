from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from models import User, UserCreate, Token, UserUpdate
import logging
from auth import (
    authenticate_user_credentials,
    create_access_token,
    get_current_active_user,
    get_password_hash
)
from database import db
from config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = logging.getLogger(__name__)


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    expires_in: int


@router.post("/register", response_model=User)
async def register_user(user_data: UserCreate):
    """Register a new user"""
    # Prepare user data for Supabase
    user_metadata = {
        "full_name": user_data.full_name,
        "avatar_url": user_data.avatar_url,
        "phone_number": user_data.phone_number,
        "role": "user",
        "is_active": True
    }
    
    # Create user in Supabase (this now handles duplicate checking)
    result = await db.create_user(
        email=user_data.email,
        password=user_data.password,
        user_data=user_metadata
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    
    # Get the created user profile
    user_profile = await db.get_user_profile(result["user"].id)
    if not user_profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User created but profile not found"
        )
    return User(**user_profile)


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return access token"""
    try:
        # Log the request details
        logger.info(f"🔍 Login attempt received")
        logger.info(f"📧 Content-Type: {request.headers.get('content-type')}")
        logger.info(f"👤 Username: {form_data.username}")
        logger.info(f"🔐 Password provided: {bool(form_data.password)}")
        logger.info(f"🔐 Password length: {len(form_data.password) if form_data.password else 0}")
        logger.info(f"📝 All headers: {dict(request.headers)}")
        
        if not form_data.username:
            logger.error("❌ No username provided")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Username is required"
            )
        
        if not form_data.password:
            logger.error("❌ No password provided")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password is required"
            )
        
        logger.info(f"🔍 Attempting authentication for: {form_data.username}")
        # Authenticate with Supabase to get session (includes refresh token)
        auth_result = await db.authenticate_user(form_data.username, form_data.password)
        if not auth_result.get("success") or not auth_result.get("user"):
            logger.warning(f"❌ Authentication failed for user: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sb_user = auth_result["user"]
        session = auth_result.get("session")

        # Ensure profile exists
        ensured_profile = await db.ensure_user_profile(sb_user)
        if not ensured_profile:
            logger.error("❌ Profile ensure failed after login")
            raise HTTPException(status_code=500, detail="Profile not found after login")

        # Issue our API access token (JWT)
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": sb_user.id}, expires_delta=access_token_expires
        )

        refresh_token = getattr(session, "refresh_token", None) if session else None
        if not refresh_token:
            logger.warning("⚠️ No refresh_token returned from Supabase session")

        logger.info(f"🎟️ Access token created for user: {sb_user.id}")
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            refresh_token=refresh_token or "",
            expires_in=int(settings.access_token_expire_minutes * 60)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )


@router.get("/me", response_model=User)
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """Get current user profile"""
    return current_user


@router.put("/me", response_model=User)
async def update_current_user_profile(
    user_updates: UserUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update current user profile"""
    update_data = user_updates.dict(exclude_unset=True)
    
    if update_data:
        success = await db.update_user_profile(current_user.id, update_data)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update profile"
            )
    
    # Return updated user profile
    updated_profile = await db.get_user_profile(current_user.id)
    return User(**updated_profile)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_access_token(current_user: User = Depends(get_current_active_user)):
    """Issue a new short-lived API access token for the authenticated user.

    The frontend should call this endpoint when nearing expiry. We do not require
    a Supabase refresh token here; we simply mint a new API JWT for the current user.
    """
    try:
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        token = create_access_token(data={"sub": current_user.id}, expires_delta=access_token_expires)
        return RefreshTokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=int(settings.access_token_expire_minutes * 60)
        )
    except Exception as e:
        logger.error(f"💥 Refresh token error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh access token"
        )
