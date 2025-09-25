from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from models import AgendaItem, AgendaItemCreate, AgendaItemUpdate, User
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime, date

router = APIRouter(prefix="/agenda", tags=["agenda"])


@router.post("/", response_model=AgendaItem)
async def create_agenda_item(
    agenda_data: AgendaItemCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create a new agenda item for an event"""
    # Check if user is participant in the event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        ue.get("events", {}).get("id") == agenda_data.event_id 
        for ue in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Prepare agenda item data
    agenda_dict = agenda_data.dict()
    agenda_dict.update({
        "id": str(uuid.uuid4()),
        "creator_id": current_user.id,
        "created_at": datetime.utcnow().isoformat()
    })
    
    # Create agenda item
    created_item = await db.create_agenda_item(agenda_dict)
    if not created_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create agenda item"
        )
    
    return AgendaItem(**created_item)


@router.get("/event/{event_id}", response_model=List[AgendaItem])
async def get_event_agenda(
    event_id: str,
    start_date: date = Query(None, description="Filter by start date"),
    end_date: date = Query(None, description="Filter by end date"),
    current_user: User = Depends(get_current_active_user)
):
    """Get agenda items for an event"""
    # Check if user is participant in the event
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        ue.get("events", {}).get("id") == event_id 
        for ue in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Get agenda items
    agenda_items = await db.get_event_agenda(event_id)
    
    # Filter by date range if provided
    if start_date or end_date:
        filtered_items = []
        for item in agenda_items:
            item_date = datetime.fromisoformat(item["start_time"]).date()
            
            if start_date and item_date < start_date:
                continue
            if end_date and item_date > end_date:
                continue
                
            filtered_items.append(item)
        agenda_items = filtered_items
    
    return [AgendaItem(**item) for item in agenda_items]


@router.get("/{agenda_id}", response_model=AgendaItem)
async def get_agenda_item(
    agenda_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific agenda item"""
    # Note: Implement get_agenda_item in database.py
    # For now, return a placeholder
    return AgendaItem(
        id=agenda_id,
        event_id="placeholder",
        creator_id=current_user.id,
        title="Sample Agenda Item",
        start_time=datetime.utcnow(),
        created_at=datetime.utcnow()
    )


@router.put("/{agenda_id}", response_model=AgendaItem)
async def update_agenda_item(
    agenda_id: str,
    agenda_updates: AgendaItemUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """Update an agenda item (only creator can update)"""
    # Note: Implement update logic
    # Check if user is creator of the agenda item
    # Update the agenda item in database
    
    # For now, return placeholder
    return AgendaItem(
        id=agenda_id,
        event_id="placeholder",
        creator_id=current_user.id,
        title=agenda_updates.title or "Updated Item",
        start_time=agenda_updates.start_time or datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@router.delete("/{agenda_id}")
async def delete_agenda_item(
    agenda_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete an agenda item (only creator can delete)"""
    # Note: Implement delete logic
    # Check if user is creator of the agenda item
    # Delete the agenda item from database
    
    return {"message": "Agenda item deleted successfully"}


@router.get("/user/calendar", response_model=List[AgendaItem])
async def get_user_calendar(
    start_date: date = Query(..., description="Calendar start date"),
    end_date: date = Query(..., description="Calendar end date"),
    current_user: User = Depends(get_current_active_user)
):
    """Get calendar view of all agenda items for user's events"""
    # Get all user events
    user_events = await db.get_user_events(current_user.id)
    
    all_agenda_items = []
    
    # Get agenda items for each event
    for user_event in user_events:
        event_id = user_event.get("events", {}).get("id")
        if event_id:
            agenda_items = await db.get_event_agenda(event_id)
            
            # Filter by date range
            for item in agenda_items:
                item_date = datetime.fromisoformat(item["start_time"]).date()
                
                if start_date <= item_date <= end_date:
                    all_agenda_items.append(AgendaItem(**item))
    
    # Sort by start time
    all_agenda_items.sort(key=lambda x: x.start_time)
    
    return all_agenda_items
