from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from models import (
    EventInvitation, EventInvitationCreate, InvitationResponse,
    EventParticipants, User
)
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post("/", response_model=EventInvitation)
async def create_invitation(
    invitation_data: EventInvitationCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create an event invitation"""
    # Check if user is participant in event (only participants can invite)
    user_events = await db.get_user_events(current_user.id)
    is_participant = any(
        event.get("id") == invitation_data.event_id 
        for event in user_events
    )
    
    if not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this event"
        )
    
    # Check if invitee is already a participant
    invitee_events = await db.get_user_events(invitation_data.invitee_id)
    is_already_participant = any(
        event.get("id") == invitation_data.event_id 
        for event in invitee_events
    )
    
    if is_already_participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a participant in this event"
        )
    
    # Check if invitation already exists
    existing_invitations = await db.get_event_invitations(invitation_data.event_id)
    existing_invitation = any(
        inv.get("invitee_id") == invitation_data.invitee_id and inv.get("status") == "pending"
        for inv in existing_invitations
    )
    
    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already sent to this user"
        )
    
    # Create invitation
    invitation_dict = invitation_data.dict()
    invitation_dict.update({
        "id": str(uuid.uuid4()),
        "inviter_id": current_user.id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    })
    
    created_invitation = await db.create_event_invitation(invitation_dict)
    if not created_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create invitation"
        )
    
    return EventInvitation(**created_invitation)


@router.get("/event/{event_id}", response_model=List[EventInvitation])
async def get_event_invitations(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get all invitations for an event"""
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
    
    invitations = await db.get_event_invitations(event_id)
    return [EventInvitation(**inv) for inv in invitations]


@router.get("/my-invitations", response_model=List[EventInvitation])
async def get_my_invitations(
    current_user: User = Depends(get_current_active_user)
):
    """Get all pending invitations for the current user with inviter and event details"""
    try:
        invitations = await db.get_user_invitations(current_user.id)
        return [EventInvitation(**inv) for inv in invitations]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get invitations"
        )


@router.post("/respond", response_model=dict)
async def respond_to_invitation(
    response_data: InvitationResponse,
    current_user: User = Depends(get_current_active_user)
):
    """Respond to an event invitation"""
    if response_data.response not in ["accepted", "declined"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response must be 'accepted' or 'declined'"
        )
    
    success = await db.respond_to_invitation(
        response_data.invitation_id,
        current_user.id,
        response_data.response
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to respond to invitation"
        )
    
    # If invitation was accepted, add user to video call
    if response_data.response == "accepted":
        try:
            # Get the invitation to find the event_id
            invitation = (await db.client.table("event_invitations")
                            .select("event_id")
                            .eq("id", response_data.invitation_id)
                            .single()
                            .execute()).data
            
            if invitation:
                event_id = invitation["event_id"]
                # Get the video call for this event
                try:
                    response = db.client.table("video_calls").select("*").eq("event_id", event_id).eq("is_active", True).limit(1).execute()
                    if response.data:
                        event_video_call = response.data[0]
                        participants = event_video_call.get("participants", [])
                        if current_user.id not in participants:
                            participants.append(current_user.id)
                        await db.update_video_call(event_video_call["id"], {"participants": participants})
                except Exception as e:
                    print(f"Error adding user to video call after invitation acceptance: {e}")
        except Exception as e:
            print(f"Error processing video call addition after invitation acceptance: {e}")
    
    return {
        "success": True,
        "message": f"Invitation {response_data.response} successfully"
    }


@router.get("/event/{event_id}/participants", response_model=EventParticipants)
async def get_event_participants_and_invitations(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get all participants and invitations for an event"""
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
    
    # Get participants and invitations
    participants_data = await db.get_event_participants(event_id)
    invitations_data = await db.get_event_invitations(event_id)

    # Convert participants data to User objects
    participants = []
    for p in participants_data:
        if p.get("user"):
            try:
                # Ensure all required fields are present with defaults
                user_data = p["user"]
                print(f"🔍 Raw user data: {user_data}")  # Debug logging
                
                user_data.setdefault("role", "user")
                user_data.setdefault("is_active", True)
                user_data.setdefault("last_seen", None)
                user_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                user_data.setdefault("updated_at", None)
                
                print(f"🔍 Processed user data: {user_data}")  # Debug logging
                user_obj = User(**user_data)
                print(f"🔍 Created User object: {user_obj}")  # Debug logging
                participants.append(user_obj)
            except Exception as e:
                print(f"Error creating User object: {e}")
                print(f"User data: {user_data}")
                continue

    # Ensure event creator is included as a participant
    try:
        event_data = await db.get_event(event_id)
        if event_data and event_data.get("creator_id"):
            creator_id = event_data["creator_id"]
            already_included = any(u.id == creator_id for u in participants)
            if not already_included:
                creator_profile = await db.get_user_profile(creator_id)
                if creator_profile:
                    # Apply defaults expected by User model
                    creator_profile.setdefault("role", "user")
                    creator_profile.setdefault("is_active", True)
                    creator_profile.setdefault("last_seen", None)
                    creator_profile.setdefault("updated_at", None)
                    try:
                        participants.append(User(**creator_profile))
                    except Exception as e:
                        print(f"Error adding creator to participants: {e}")
    except Exception as e:
        print(f"Error ensuring creator in participants: {e}")
    
    # Convert invitations data to EventInvitation objects with proper user data
    invitations = []
    for inv in invitations_data:
        try:
            # Process inviter data
            inviter_data = inv.get("inviter", {})
            if inviter_data:
                inviter_data.setdefault("role", "user")
                inviter_data.setdefault("is_active", True)
                inviter_data.setdefault("last_seen", None)
                inviter_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                inviter_data.setdefault("updated_at", None)
                inv["inviter"] = User(**inviter_data)
            else:
                inv["inviter"] = None
            
            # Process invitee data
            invitee_data = inv.get("invitee", {})
            if invitee_data:
                invitee_data.setdefault("role", "user")
                invitee_data.setdefault("is_active", True)
                invitee_data.setdefault("last_seen", None)
                invitee_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                invitee_data.setdefault("updated_at", None)
                inv["invitee"] = User(**invitee_data)
            else:
                inv["invitee"] = None
            
            print(f"🔍 Processed invitation: {inv}")  # Debug logging
            invitations.append(EventInvitation(**inv))
        except Exception as e:
            print(f"Error creating EventInvitation object: {e}")
            print(f"Invitation data: {inv}")
            continue
    
    return EventParticipants(
        participants=participants,
        invitations=invitations
    )
