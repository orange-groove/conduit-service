from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from models import Message, MessageCreate, MessageWithSender, User
from auth import get_current_active_user
from database import db
import uuid
from datetime import datetime
import json

router = APIRouter(prefix="/messages", tags=["messaging"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: dict = {}  # user_id -> websocket
        self.event_connections: dict = {}  # event_id -> [user_ids]
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections[user_id] = websocket
        print(f"🔌 User {user_id} connected to messaging WebSocket")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        print(f"🔌 User {user_id} disconnected from messaging WebSocket")
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.user_connections:
            websocket = self.user_connections[user_id]
            await websocket.send_text(message)
            print(f"📤 Sent direct message to user {user_id}")
        else:
            print(f"❌ User {user_id} not connected for direct message")
    
    async def send_event_message(self, message: str, event_id: str, sender_id: str):
        # Get all participants of the event from database
        try:
            participants = await db.get_event_participants(event_id)
            if participants:
                for participant in participants:
                    user_id = participant.get("user_id")
                    if user_id and user_id != sender_id and user_id in self.user_connections:
                        websocket = self.user_connections[user_id]
                        await websocket.send_text(message)
                        print(f"📤 Sent event message to participant {user_id}")
            else:
                print(f"❌ No participants found for event {event_id}")
        except Exception as e:
            print(f"❌ Error sending event message: {e}")
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages
            try:
                message_data = json.loads(data)
                await handle_websocket_message(message_data, user_id)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "error": "Invalid JSON format"
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)


async def handle_websocket_message(message_data: dict, sender_id: str):
    """Handle incoming WebSocket messages"""
    message_type = message_data.get("type")
    
    if message_type == "send_message":
        # Handle undefined/null values from frontend
        event_id = message_data.get("event_id")
        recipient_id = message_data.get("recipient_id")
        
        # Convert undefined to None for proper handling
        if event_id == "undefined" or event_id is None:
            event_id = None
        if recipient_id == "undefined" or recipient_id is None:
            recipient_id = None
            
        print(f"📨 WebSocket message from {sender_id}: event_id={event_id}, recipient_id={recipient_id}")
        
        # Validate message has either event_id or recipient_id
        if not event_id and not recipient_id:
            print(f"❌ Message missing both event_id and recipient_id")
            return
        
        # Create and store message
        message_create = MessageCreate(
            content=message_data.get("content", ""),
            message_type=message_data.get("message_type", "text"),
            event_id=event_id,
            recipient_id=recipient_id,
            metadata=message_data.get("metadata")
        )
        
        # Save message to database
        message_dict = message_create.dict()
        message_dict.update({
            "id": str(uuid.uuid4()),
            "sender_id": sender_id,
            "created_at": datetime.utcnow().isoformat(),
            "is_read": False
        })
        
        stored_message = await db.send_message(message_dict)
        if stored_message:
            print(f"✅ Message stored successfully: {stored_message['id']}")
            # Send to recipients
            if message_create.event_id:
                # Event message
                print(f"📤 Broadcasting event message to event {message_create.event_id}")
                await manager.send_event_message(
                    json.dumps({
                        "type": "new_message",
                        "message": stored_message
                    }),
                    message_create.event_id,
                    sender_id
                )
            elif message_create.recipient_id:
                # Direct message
                print(f"📤 Sending direct message to user {message_create.recipient_id}")
                await manager.send_personal_message(
                    json.dumps({
                        "type": "new_message",
                        "message": stored_message
                    }),
                    message_create.recipient_id
                )
        else:
            print(f"❌ Failed to store message")


@router.post("/", response_model=Message)
async def send_message(
    message_data: MessageCreate,
    current_user: User = Depends(get_current_active_user)
):
    """Send a message via HTTP (fallback for non-WebSocket clients)"""
    # Validate message
    if not message_data.event_id and not message_data.recipient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message must have either event_id or recipient_id"
        )
    
    # Prepare message data
    message_dict = message_data.dict()
    message_dict.update({
        "id": str(uuid.uuid4()),
        "sender_id": current_user.id,
        "created_at": datetime.utcnow().isoformat(),
        "is_read": False
    })
    
    # Save message
    stored_message = await db.send_message(message_dict)
    if not stored_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to send message"
        )
    
    # Notify via WebSocket
    if message_data.event_id:
        await manager.send_event_message(
            json.dumps({
                "type": "new_message",
                "message": stored_message
            }),
            message_data.event_id,
            current_user.id
        )
    elif message_data.recipient_id:
        await manager.send_personal_message(
            json.dumps({
                "type": "new_message", 
                "message": stored_message
            }),
            message_data.recipient_id
        )
    
    return Message(**stored_message)


@router.get("/direct/{other_user_id}", response_model=List[MessageWithSender])
async def get_direct_messages(
    other_user_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user)
):
    """Get direct messages between current user and another user"""
    messages = await db.get_direct_messages(current_user.id, other_user_id, limit)
    
    # Convert to MessageWithSender format
    result = []
    for msg in messages:
        sender_data = msg.pop("sender", {})
        
        # Handle missing or invalid sender data
        sender_user = None
        if sender_data and isinstance(sender_data, dict) and sender_data.get("id"):
            try:
                # Ensure required fields are present with defaults
                sender_data.setdefault("role", "user")
                sender_data.setdefault("is_active", True)
                sender_data.setdefault("last_seen", None)
                sender_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                sender_data.setdefault("updated_at", None)
                
                sender_user = User(**sender_data)
            except Exception as e:
                print(f"Error creating User object for sender: {e}")
                print(f"Sender data: {sender_data}")
                # Create a minimal user object with just the ID
                sender_user = User(
                    id=sender_data.get("id", "unknown"),
                    email="unknown@example.com",
                    full_name=sender_data.get("full_name", "Unknown User"),
                    avatar_url=sender_data.get("avatar_url"),
                    phone_number=None,
                    role="user",
                    is_active=True,
                    last_seen=None,
                    created_at="2024-01-01T00:00:00Z",
                    updated_at=None
                )
        
        message_with_sender = MessageWithSender(
            **msg,
            sender=sender_user
        )
        result.append(message_with_sender)
    
    return result


@router.get("/event/{event_id}", response_model=List[MessageWithSender])
async def get_event_messages(
    event_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user)
):
    """Get messages for an event (group chat)"""
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
    
    messages = await db.get_event_messages(event_id, limit)
    
    # Convert to MessageWithSender format
    result = []
    for msg in messages:
        sender_data = msg.pop("sender", {})
        
        # Handle missing or invalid sender data
        sender_user = None
        if sender_data and isinstance(sender_data, dict) and sender_data.get("id"):
            try:
                # Ensure required fields are present with defaults
                sender_data.setdefault("role", "user")
                sender_data.setdefault("is_active", True)
                sender_data.setdefault("last_seen", None)
                sender_data.setdefault("created_at", "2024-01-01T00:00:00Z")
                sender_data.setdefault("updated_at", None)
                
                sender_user = User(**sender_data)
            except Exception as e:
                print(f"Error creating User object for sender: {e}")
                print(f"Sender data: {sender_data}")
                # Create a minimal user object with just the ID
                sender_user = User(
                    id=sender_data.get("id", "unknown"),
                    email="unknown@example.com",
                    full_name=sender_data.get("full_name", "Unknown User"),
                    avatar_url=sender_data.get("avatar_url"),
                    phone_number=None,
                    role="user",
                    is_active=True,
                    last_seen=None,
                    created_at="2024-01-01T00:00:00Z",
                    updated_at=None
                )
        
        message_with_sender = MessageWithSender(
            **msg,
            sender=sender_user
        )
        result.append(message_with_sender)
    
    return result


@router.put("/{message_id}/read")
async def mark_message_read(
    message_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Mark a message as read"""
    # Note: Implement in database.py
    # For now, return success
    return {"message": "Message marked as read"}
