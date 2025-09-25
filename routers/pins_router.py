from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from models import (
    EventPin, EventPinCreate, EventPinUpdate, EventPinWithCreator,
    PinType, User
)
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime

router = APIRouter(prefix="/pins", tags=["event pins"])


@router.post("/", response_model=EventPin)
async def create_event_pin(
    pin_data: EventPinCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create a new event pin"""
    # Check if user is participant in event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == pin_data.event_id 
        for event in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Prepare pin data
    pin_dict = pin_data.dict()
    pin_dict.update({
        "id": str(uuid.uuid4()),
        "creator_id": current_user.id,
        "created_at": datetime.utcnow().isoformat()
    })
    
    # Create pin in database
    created_pin = await db.create_event_pin(pin_dict)
    if not created_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create event pin"
        )
    
    return EventPin(**created_pin)


@router.get("/event/{event_id}", response_model=List[EventPinWithCreator])
async def get_event_pins(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get all pins for an event"""
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
    
    pins_data = await db.get_event_pins(event_id)
    
    # Convert to EventPinWithCreator objects
    pins = []
    for pin_data in pins_data:
        try:
            # Process creator data
            creator_data = pin_data.pop("creator", {})
            if creator_data:
                creator_data.setdefault("role", "user")
                creator_data.setdefault("is_active", True)
                creator_data.setdefault("last_seen", None)
                creator_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                creator_data.setdefault("updated_at", None)
                pin_data["creator"] = User(**creator_data)
            else:
                pin_data["creator"] = None
            
            pins.append(EventPinWithCreator(**pin_data))
        except Exception as e:
            print(f"Error creating EventPinWithCreator object: {e}")
            print(f"Pin data: {pin_data}")
            continue
    
    return pins


@router.get("/{pin_id}", response_model=EventPinWithCreator)
async def get_event_pin(
    pin_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific event pin"""
    pin_data = await db.get_event_pin(pin_id)
    if not pin_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event pin not found"
        )
    
    # Check if user is participant in the event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == pin_data["event_id"] 
        for event in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Process creator data
    creator_data = pin_data.pop("creator", {})
    if creator_data:
        creator_data.setdefault("role", "user")
        creator_data.setdefault("is_active", True)
        creator_data.setdefault("last_seen", None)
        creator_data.setdefault("created_at", "2024-01-01T00:00:00Z")
        creator_data.setdefault("updated_at", None)
        pin_data["creator"] = User(**creator_data)
    else:
        pin_data["creator"] = None
    
    return EventPinWithCreator(**pin_data)


@router.put("/{pin_id}", response_model=EventPin)
async def update_event_pin(
    pin_id: str,
    pin_updates: EventPinUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update an event pin"""
    # Get existing pin
    pin_data = await db.get_event_pin(pin_id)
    if not pin_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event pin not found"
        )
    
    # Check if user is the creator
    if pin_data["creator_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the pin creator can update this pin"
        )
    
    # Prepare updates
    update_data = pin_updates.dict(exclude_unset=True)
    
    # Update pin in database
    success = await db.update_event_pin(pin_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update event pin"
        )
    
    # Get updated pin
    updated_pin = await db.get_event_pin(pin_id)
    return EventPin(**updated_pin)


@router.delete("/{pin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event_pin(
    pin_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete an event pin"""
    # Get existing pin
    pin_data = await db.get_event_pin(pin_id)
    if not pin_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event pin not found"
        )
    
    # Check if user is the creator
    if pin_data["creator_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the pin creator can delete this pin"
        )
    
    # Delete pin
    success = await db.delete_event_pin(pin_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete event pin"
        )


@router.get("/event/{event_id}/type/{pin_type}", response_model=List[EventPinWithCreator])
async def get_pins_by_type(
    event_id: str,
    pin_type: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get pins of a specific type for an event"""
    # Validate pin type
    if pin_type not in [pt.value for pt in PinType]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid pin type. Must be one of: {[pt.value for pt in PinType]}"
        )
    
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
    
    pins_data = await db.get_pins_by_type(event_id, pin_type)
    
    # Convert to EventPinWithCreator objects
    pins = []
    for pin_data in pins_data:
        try:
            # Process creator data
            creator_data = pin_data.pop("creator", {})
            if creator_data:
                creator_data.setdefault("role", "user")
                creator_data.setdefault("is_active", True)
                creator_data.setdefault("last_seen", None)
                creator_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                creator_data.setdefault("updated_at", None)
                pin_data["creator"] = User(**creator_data)
            else:
                pin_data["creator"] = None
            
            pins.append(EventPinWithCreator(**pin_data))
        except Exception as e:
            print(f"Error creating EventPinWithCreator object: {e}")
            print(f"Pin data: {pin_data}")
            continue
    
    return pins


@router.get("/event/{event_id}/bounds", response_model=List[EventPinWithCreator])
async def get_pins_in_bounds(
    event_id: str,
    north: float = Query(..., description="Northern boundary latitude"),
    south: float = Query(..., description="Southern boundary latitude"),
    east: float = Query(..., description="Eastern boundary longitude"),
    west: float = Query(..., description="Western boundary longitude"),
    current_user: User = Depends(get_current_active_user)
):
    """Get pins within geographic bounds for an event"""
    # Validate bounds
    if north <= south:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="North latitude must be greater than south latitude"
        )
    if east <= west:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="East longitude must be greater than west longitude"
        )
    
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
    
    pins_data = await db.get_pins_in_bounds(event_id, north, south, east, west)
    
    # Convert to EventPinWithCreator objects
    pins = []
    for pin_data in pins_data:
        try:
            # Process creator data
            creator_data = pin_data.pop("creator", {})
            if creator_data:
                creator_data.setdefault("role", "user")
                creator_data.setdefault("is_active", True)
                creator_data.setdefault("last_seen", None)
                creator_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                creator_data.setdefault("updated_at", None)
                pin_data["creator"] = User(**creator_data)
            else:
                pin_data["creator"] = None
            
            pins.append(EventPinWithCreator(**pin_data))
        except Exception as e:
            print(f"Error creating EventPinWithCreator object: {e}")
            print(f"Pin data: {pin_data}")
            continue
    
    return pins
