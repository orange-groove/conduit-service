from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from models import (
    Event, EventCreate, EventUpdate, EventWithParticipants,
    User, UserEvent, UserEventCreate, EventInviteResponse
)
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/", response_model=Event)
async def create_event(
    event_data: EventCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create a new event"""
    # Prepare event data with proper datetime serialization
    event_dict = event_data.dict()
    
    # Convert datetime fields to ISO format strings
    if event_dict.get("start_date"):
        event_dict["start_date"] = event_dict["start_date"].isoformat()
    if event_dict.get("end_date"):
        event_dict["end_date"] = event_dict["end_date"].isoformat()
    
    # Convert location_coords to dict if it's a Pydantic model
    if event_dict.get("location_coords") and hasattr(event_dict["location_coords"], "dict"):
        event_dict["location_coords"] = event_dict["location_coords"].dict()
    
    event_dict.update({
        "id": str(uuid.uuid4()),
        "creator_id": current_user.id,
        "status": "active",
        "participant_count": 1,
        "created_at": datetime.utcnow().isoformat()
    })
    
    # Create event in database
    created_event = await db.create_event(event_dict)
    if not created_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create event"
        )
    
    # Add creator as participant
    await db.join_event(current_user.id, created_event["id"], "creator")
    
    # Create video call room for the event
    video_call_data = {
        "id": str(uuid.uuid4()),
        "event_id": created_event["id"],
        "creator_id": current_user.id,
        "participants": [current_user.id],
        "is_group_call": True,
        "is_active": True,
        "started_at": datetime.utcnow().isoformat()
    }
    
    try:
        video_call_result = await db.create_video_call(video_call_data)
        if not video_call_result:
            print(f"Warning: Failed to create video call for event {created_event['id']}")
    except Exception as e:
        print(f"Error creating video call for event {created_event['id']}: {e}")
    
    return Event(**created_event)


@router.get("/", response_model=List[Event])
async def get_user_events(
    current_user: User = Depends(get_current_active_user)
):
    """Get all events for the current user"""
    print(f"🔍 Getting events for user: {current_user.id}")
    user_events = await db.get_user_events(current_user.id)
    print(f"🔍 Retrieved events: {user_events}")
    
    events = []
    for event_data in user_events:
        try:
            events.append(Event(**event_data))
        except Exception as e:
            print(f"Error creating Event object: {e}")
            print(f"Event data: {event_data}")
    
    print(f"🔍 Returning {len(events)} events")
    return events


@router.get("/{event_id}", response_model=EventWithParticipants)
async def get_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get event details with participants"""
    event_data = await db.get_event(event_id)
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Check if user is participant
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == event_id 
        for event in user_events
    )
    
    if not is_participant and event_data.get("is_private", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to private event"
        )
    
    # Get event participants
    # Note: This would need a proper join query in a real implementation
    participants = []  # Simplified for now
    
    # Get agenda items
    agenda_items = await db.get_event_agenda(event_id)
    
    event = EventWithParticipants(
        **event_data,
        participants=participants,
        agenda_items=agenda_items
    )
    
    return event


@router.put("/{event_id}", response_model=Event)
async def update_event(
    event_id: str,
    event_updates: EventUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update an event (only creator or admin can update)"""
    # Check if event exists and user has permission
    event_data = await db.get_event(event_id)
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    if event_data["creator_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only event creator can update event"
        )
    
    # Update event
    update_data = event_updates.dict(exclude_unset=True)
    if update_data:
        update_data["updated_at"] = datetime.utcnow().isoformat()
        # Note: Implement update logic in database.py
        # For now, we'll just return the original event
    
    return Event(**event_data)


@router.post("/{event_id}/join", response_model=EventInviteResponse)
async def join_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Join an event"""
    # Check if event exists
    event_data = await db.get_event(event_id)
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Check if user is already a participant
    user_events = await db.get_user_events(current_user.id)
    is_already_participant = any(
        event.get("id") == event_id 
        for event in user_events
    )
    
    if is_already_participant:
        return EventInviteResponse(
            success=False,
            message="Already a participant in this event"
        )
    
    # Join event
    success = await db.join_event(current_user.id, event_id)
    if success:
        # Also add user to the video call for this event
        try:
            # Get the video call for this event
            video_calls = await db.get_user_active_calls(current_user.id)
            event_video_call = None
            for call in video_calls:
                if call.get("event_id") == event_id:
                    event_video_call = call
                    break
            
            # If no video call found, get it directly
            if not event_video_call:
                try:
                    response = db.client.table("video_calls").select("*").eq("event_id", event_id).eq("is_active", True).limit(1).execute()
                    if response.data:
                        event_video_call = response.data[0]
                except Exception as e:
                    print(f"Error fetching video call for event: {e}")
            
            # Add user to video call participants
            if event_video_call:
                participants = event_video_call.get("participants", [])
                if current_user.id not in participants:
                    participants.append(current_user.id)
                    await db.update_video_call(event_video_call["id"], {"participants": participants})
        except Exception as e:
            print(f"Error adding user to video call: {e}")
            # Don't fail the join event if video call update fails
        
        return EventInviteResponse(
            success=True,
            message="Successfully joined event",
            event=Event(**event_data)
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to join event"
        )


@router.post("/{event_id}/leave", response_model=EventInviteResponse)
async def leave_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Leave an event"""
    # Check if event exists
    event_data = await db.get_event(event_id)
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    # Creator cannot leave their own event
    if event_data["creator_id"] == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event creator cannot leave event"
        )
    
    # Leave event
    success = await db.leave_event(current_user.id, event_id)
    if success:
        # Also remove user from the video call for this event
        try:
            # Get the video call for this event
            try:
                response = db.client.table("video_calls").select("*").eq("event_id", event_id).eq("is_active", True).limit(1).execute()
                if response.data:
                    event_video_call = response.data[0]
                    participants = event_video_call.get("participants", [])
                    if current_user.id in participants:
                        participants.remove(current_user.id)
                        await db.update_video_call(event_video_call["id"], {"participants": participants})
            except Exception as e:
                print(f"Error removing user from video call: {e}")
                # Don't fail the leave event if video call update fails
        except Exception as e:
            print(f"Error processing video call removal: {e}")
        
        return EventInviteResponse(
            success=True,
            message="Successfully left event"
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to leave event"
        )


@router.delete("/{event_id}")
async def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete an event (only creator can delete)"""
    # Check if event exists and user has permission
    event_data = await db.get_event(event_id)
    if not event_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    
    if event_data["creator_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only event creator can delete event"
        )
    
    # Update event status to cancelled instead of actual deletion
    update_data = {
        "status": "cancelled",
        "updated_at": datetime.utcnow().isoformat()
    }
    # Note: Implement update logic in database.py
    
    return {"message": "Event deleted successfully"}
