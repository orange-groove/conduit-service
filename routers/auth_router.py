from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from models import User, UserCreate, Token, UserUpdate
import logging
from jose import JWTError, jwt
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
    try:
        # Check Supabase client initialization
        if not db.client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection not available"
            )
        
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
            error_message = result["message"]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # Get the created user profile
        user_profile = await db.get_user_profile(result["user"].id)
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User created but profile not found"
            )
        
        return User(**user_profile)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


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
async def refresh_access_token(request: Request):
    """Refresh the access token using the current (possibly expired) token.
    
    This endpoint validates the current token (even if expired) and issues a new one.
    """
    try:
        print(f"🔍 Refresh token request received")
        
        # Get the authorization header
        auth_header = request.headers.get("Authorization")
        print(f"🔍 Auth header: {auth_header}")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            print("❌ Missing or invalid authorization header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )
        
        # Extract the current token (even if expired)
        current_token = auth_header.split(" ")[1]
        print(f"🔍 Current token: {current_token[:20]}...")
        
        # Decode the token to get user ID (even if expired)
        try:
            payload = jwt.decode(current_token, settings.secret_key, algorithms=[settings.algorithm], options={"verify_exp": False})
            user_id = payload.get("sub")
            print(f"🔍 Decoded user ID: {user_id}")
            
            if not user_id:
                print("❌ Invalid token payload - no user ID")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
        except jwt.JWTError as e:
            print(f"❌ JWT decode error: {e}")
            logger.error(f"Invalid token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Verify user still exists and is active
        print(f"🔍 Checking user profile for: {user_id}")
        user_profile = await db.get_user_profile(user_id)
        print(f"🔍 User profile: {user_profile}")
        
        if not user_profile:
            print("❌ User not found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        if not user_profile.get("is_active", True):
            print("❌ User account is inactive")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )
        
        # Create new access token
        print(f"🔍 Creating new token for user: {user_id}")
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        new_token = create_access_token(
            data={"sub": user_id}, 
            expires_delta=access_token_expires
        )
        
        print(f"✅ Token refreshed successfully for user: {user_id}")
        logger.info(f"✅ Token refreshed for user: {user_id}")
        return RefreshTokenResponse(
            access_token=new_token,
            token_type="bearer",
            expires_in=int(settings.access_token_expire_minutes * 60)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Refresh token error: {e}")
        logger.error(f"💥 Refresh token error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh access token"
        )
