from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from models import User
from auth import get_current_active_user
from database import db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=List[User])
async def search_users(
    q: str = Query(..., min_length=2, description="Search query (email or name)"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of results"),
    current_user: User = Depends(get_current_active_user)
):
    """Search users by email or name for inviting to events"""
    if len(q.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query must be at least 2 characters"
        )
    
    users = await db.search_users(q.strip(), limit)
    return [User(**user) for user in users]


@router.get("/by-email/{email}", response_model=User)
async def get_user_by_email(
    email: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get user by exact email match"""
    user_data = await db.get_user_by_email(email)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return User(**user_data)


@router.get("/me", response_model=User)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user's profile"""
    return current_user


@router.get("/{user_id}", response_model=User)
async def get_user_by_id(
    user_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get a user's profile by their ID"""
    user_data = await db.get_user_profile(user_id)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return User(**user_data)
