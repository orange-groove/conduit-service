from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from models import UserLocation, UserLocationCreate, User, UserCurrentLocation
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime
from pydantic import BaseModel

router = APIRouter(prefix="/location", tags=["location"])


class LocationSharingRequest(BaseModel):
    is_shared: bool


@router.post("/update", response_model=UserCurrentLocation)
async def update_location(
    location_data: UserLocationCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Update user's current location using optimized UPSERT approach"""
    # Prepare location data
    location_dict = location_data.dict()
    location_dict.update({
        "user_id": current_user.id,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Update location in database using UPSERT
    success = await db.update_user_location(current_user.id, location_dict)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update location"
        )
    
    # Get the updated location from database to return proper response
    updated_location = await db.get_user_current_location(current_user.id)
    if not updated_location:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated location"
        )
    
    return UserCurrentLocation(**updated_location)


@router.get("/me", response_model=UserCurrentLocation)
async def get_my_location(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user's location"""
    location = await db.get_user_current_location(current_user.id)
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found"
        )
    
    return UserCurrentLocation(**location)


@router.post("/sharing")
async def toggle_location_sharing(
    request: LocationSharingRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Enable/disable location sharing"""
    success = await db.set_location_sharing(current_user.id, request.is_shared)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update location sharing"
        )
    
    return {"is_shared": request.is_shared}


@router.get("/event/{event_id}")
async def get_event_locations(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get current locations of all event participants who have shared their location"""
    # Check if user is participant in event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == event_id 
        for event in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Get event locations (only users who have shared their location)
    locations = await db.get_event_locations(event_id)
    
    return locations


@router.get("/user/{user_id}")
async def get_user_location(
    user_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get location of a specific user (only if in same event or direct friends)"""
    # Note: This would require implementing friend relationships
    # For now, allow if users share any active events
    
    current_user_events = await db.get_user_events(current_user.id)
    target_user_events = await db.get_user_events(user_id)
    
    # Check if users share any events
    current_event_ids = {event.get("id") for event in current_user_events}
    target_event_ids = {event.get("id") for event in target_user_events}
    
    shared_events = current_event_ids.intersection(target_event_ids)
    
    if not shared_events:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: no shared events with this user"
        )
    
    # Get latest location for the user
    # Note: Implement get_user_latest_location in database.py
    # For now, return a placeholder
    return {"message": "Location access granted", "user_id": user_id}


@router.get("/event/{event_id}/latest")
async def get_event_participants_latest_locations(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Return all active participants with their latest location (or null).

    Response: [{ user: User, location: UserLocation | null }]
    """
    # Check if user is participant in event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == event_id 
        for event in user_events
    )
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )

    merged = await db.get_event_participants_with_latest_location(event_id)

    # Cast nested user/location into expected shapes
    response: List[Dict[str, Any]] = []
    for entry in merged:
        user_data = entry.get("user") or {}
        location_data = entry.get("location") or None
        try:
            user_obj = User(**user_data)
        except Exception:
            continue
        loc_obj = UserLocation(**location_data) if location_data else None
        response.append({
            "user": user_obj.dict(),
            "location": loc_obj.dict() if loc_obj else None
        })

    return response
