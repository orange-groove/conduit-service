from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from models import VideoCall, VideoCallCreate, User
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime
import json

router = APIRouter(prefix="/video", tags=["video-chat"])


class VideoConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # call_id -> websocket
        self.call_participants: Dict[str, List[str]] = {}  # call_id -> [user_ids]
        self.user_calls: Dict[str, str] = {}  # user_id -> call_id
    
    async def connect(self, websocket: WebSocket, call_id: str, user_id: str):
        await websocket.accept()
        
        if call_id not in self.active_connections:
            self.active_connections[call_id] = {}
        if call_id not in self.call_participants:
            self.call_participants[call_id] = []
            
        self.active_connections[call_id][user_id] = websocket
        if user_id not in self.call_participants[call_id]:
            self.call_participants[call_id].append(user_id)
        self.user_calls[user_id] = call_id
    
    def disconnect(self, call_id: str, user_id: str):
        if call_id in self.active_connections and user_id in self.active_connections[call_id]:
            del self.active_connections[call_id][user_id]
        
        if call_id in self.call_participants and user_id in self.call_participants[call_id]:
            self.call_participants[call_id].remove(user_id)
        
        if user_id in self.user_calls:
            del self.user_calls[user_id]
    
    async def send_to_call(self, call_id: str, message: str, exclude_user: str = None):
        if call_id in self.active_connections:
            for user_id, websocket in self.active_connections[call_id].items():
                if user_id != exclude_user:
                    try:
                        await websocket.send_text(message)
                    except:
                        # Connection might be closed
                        pass
    
    async def send_to_user(self, call_id: str, user_id: str, message: str):
        if call_id in self.active_connections and user_id in self.active_connections[call_id]:
            try:
                await self.active_connections[call_id][user_id].send_text(message)
            except:
                # Connection might be closed
                pass


video_manager = VideoConnectionManager()


@router.websocket("/ws/{call_id}/{user_id}")
async def video_websocket_endpoint(websocket: WebSocket, call_id: str, user_id: str):
    await video_manager.connect(websocket, call_id, user_id)
    
    # Notify other participants that user joined
    await video_manager.send_to_call(
        call_id,
        json.dumps({
            "type": "user_joined",
            "user_id": user_id,
            "participants": video_manager.call_participants.get(call_id, [])
        }),
        exclude_user=user_id
    )
    
    try:
        while True:
            data = await websocket.receive_text()
            await handle_video_message(data, call_id, user_id)
    except WebSocketDisconnect:
        video_manager.disconnect(call_id, user_id)
        
        # Notify other participants that user left
        await video_manager.send_to_call(
            call_id,
            json.dumps({
                "type": "user_left",
                "user_id": user_id,
                "participants": video_manager.call_participants.get(call_id, [])
            })
        )


async def handle_video_message(data: str, call_id: str, sender_id: str):
    """Handle WebRTC signaling messages"""
    try:
        message = json.loads(data)
        message_type = message.get("type")
        
        if message_type == "offer":
            # Forward offer to specific participant
            target_user = message.get("target_user")
            if target_user:
                await video_manager.send_to_user(
                    call_id,
                    target_user,
                    json.dumps({
                        "type": "offer",
                        "offer": message.get("offer"),
                        "from_user": sender_id
                    })
                )
        
        elif message_type == "answer":
            # Forward answer to specific participant
            target_user = message.get("target_user")
            if target_user:
                await video_manager.send_to_user(
                    call_id,
                    target_user,
                    json.dumps({
                        "type": "answer",
                        "answer": message.get("answer"),
                        "from_user": sender_id
                    })
                )
        
        elif message_type == "ice_candidate":
            # Forward ICE candidate to specific participant or all
            target_user = message.get("target_user")
            ice_message = json.dumps({
                "type": "ice_candidate",
                "candidate": message.get("candidate"),
                "from_user": sender_id
            })
            
            if target_user:
                await video_manager.send_to_user(call_id, target_user, ice_message)
            else:
                await video_manager.send_to_call(call_id, ice_message, exclude_user=sender_id)
        
        elif message_type == "mute" or message_type == "unmute":
            # Notify other participants about mute/unmute
            await video_manager.send_to_call(
                call_id,
                json.dumps({
                    "type": message_type,
                    "user_id": sender_id
                }),
                exclude_user=sender_id
            )
        
        elif message_type == "video_toggle":
            # Notify other participants about video on/off
            await video_manager.send_to_call(
                call_id,
                json.dumps({
                    "type": "video_toggle",
                    "user_id": sender_id,
                    "video_enabled": message.get("video_enabled", True)
                }),
                exclude_user=sender_id
            )
    
    except json.JSONDecodeError:
        pass  # Invalid JSON, ignore


@router.post("/", response_model=VideoCall)
async def create_video_call(
    call_data: VideoCallCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Create a new direct video call (not event-based)"""
    # For direct calls, validate participants
    if call_data.participants:
        for participant_id in call_data.participants:
            # Check if participant exists
            participant = await db.get_user_profile(participant_id)
            if not participant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Participant {participant_id} not found"
                )
    
    # Create video call record
    call_dict = call_data.dict()
    call_dict.update({
        "id": str(uuid.uuid4()),
        "creator_id": current_user.id,
        "is_active": True,
        "started_at": datetime.utcnow().isoformat()
    })
    
    # Add creator to participants if not already included
    if current_user.id not in call_dict.get("participants", []):
        call_dict["participants"] = call_dict.get("participants", []) + [current_user.id]
    
    # Create video call in database
    created_call = await db.create_video_call(call_dict)
    if not created_call:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create video call"
        )
    
    return VideoCall(**created_call)


@router.get("/{call_id}", response_model=VideoCall)
async def get_video_call(
    call_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get video call details"""
    call_data = await db.get_video_call(call_id)
    if not call_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video call not found"
        )
    
    # Check if user is participant or creator
    is_creator = call_data["creator_id"] == current_user.id
    is_participant = current_user.id in call_data.get("participants", [])
    
    if not is_creator and not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this call"
        )
    
    return VideoCall(**call_data)


@router.post("/{call_id}/join")
async def join_video_call(
    call_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Join an existing video call"""
    call_data = await db.get_video_call(call_id)
    if not call_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video call not found"
        )
    
    if not call_data.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video call is not active"
        )
    
    # Add user to participants if not already there
    participants = call_data.get("participants", [])
    if current_user.id not in participants:
        participants.append(current_user.id)
        await db.update_video_call(call_id, {"participants": participants})
    
    return {"message": "Joined video call", "call_id": call_id}


@router.post("/{call_id}/leave")
async def leave_video_call(
    call_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Leave a video call"""
    call_data = await db.get_video_call(call_id)
    if not call_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video call not found"
        )
    
    # Remove user from participants
    participants = call_data.get("participants", [])
    if current_user.id in participants:
        participants.remove(current_user.id)
        await db.update_video_call(call_id, {"participants": participants})
    
    # Remove user from active call
    if current_user.id in video_manager.user_calls:
        current_call_id = video_manager.user_calls[current_user.id]
        if current_call_id == call_id:
            video_manager.disconnect(call_id, current_user.id)
    
    return {"message": "Left video call", "call_id": call_id}


@router.post("/{call_id}/end")
async def end_video_call(
    call_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """End a video call (only creator can end)"""
    call_data = await db.get_video_call(call_id)
    if not call_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video call not found"
        )
    
    # Check if user is creator
    if call_data["creator_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the call creator can end the call"
        )
    
    # Mark call as inactive and set end time
    await db.update_video_call(call_id, {
        "is_active": False,
        "ended_at": datetime.utcnow().isoformat()
    })
    
    # Notify all participants that call ended
    await video_manager.send_to_call(
        call_id,
        json.dumps({
            "type": "call_ended",
            "ended_by": current_user.id
        })
    )
    
    # Disconnect all participants
    if call_id in video_manager.call_participants:
        for user_id in video_manager.call_participants[call_id].copy():
            video_manager.disconnect(call_id, user_id)
    
    return {"message": "Video call ended", "call_id": call_id}


@router.get("/", response_model=List[VideoCall])
async def get_active_calls(
    current_user: User = Depends(get_current_active_user)
):
    """Get active video calls for the user"""
    calls_data = await db.get_user_active_calls(current_user.id)
    return [VideoCall(**call_data) for call_data in calls_data]


@router.get("/event/{event_id}", response_model=VideoCall)
async def get_event_video_call(
    event_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get the video call for a specific event"""
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
    
    try:
        response = db.client.table("video_calls").select("*").eq("event_id", event_id).eq("is_active", True).limit(1).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active video call found for this event"
            )
        return VideoCall(**response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching event video call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch event video call"
        )


@router.get("/{call_id}/participants")
async def get_call_participants(
    call_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get participants in a video call"""
    call_data = await db.get_video_call(call_id)
    if not call_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video call not found"
        )
    
    # Check if user is participant or creator
    is_creator = call_data["creator_id"] == current_user.id
    is_participant = current_user.id in call_data.get("participants", [])
    
    if not is_creator and not is_participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not a participant in this call"
        )
    
    # Get participant details
    participants = call_data.get("participants", [])
    participant_details = []
    
    for user_id in participants:
        user_data = await db.get_user_profile(user_id)
        if user_data:
            participant_details.append({
                "id": user_data["id"],
                "full_name": user_data["full_name"],
                "avatar_url": user_data.get("avatar_url"),
                "is_online": user_id in video_manager.user_calls and video_manager.user_calls[user_id] == call_id
            })
    
    return {
        "call_id": call_id,
        "participants": participant_details,
        "total_participants": len(participant_details)
    }
