from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class EventStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    LOCATION = "location"
    SYSTEM = "system"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone_number: Optional[str] = None


class User(UserBase):
    id: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LocationData(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None
    timestamp: datetime


class EventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    location_coords: Optional[LocationData] = None
    is_private: bool = False

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    location: Optional[str] = None
    location_coords: Optional[LocationData] = None
    is_private: Optional[bool] = None
    status: Optional[EventStatus] = None


class Event(EventBase):
    id: str
    creator_id: str
    status: EventStatus = EventStatus.ACTIVE
    participant_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class UserEventBase(BaseModel):
    event_id: str
    role: str = "participant"  # creator, admin, participant


class UserEventCreate(UserEventBase):
    pass


class UserEvent(UserEventBase):
    user_id: str
    joined_at: datetime
    is_active: bool = True

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    content: str
    message_type: MessageType = MessageType.TEXT
    event_id: Optional[str] = None
    recipient_id: Optional[str] = None  # For direct messages
    metadata: Optional[Dict[str, Any]] = None


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: str
    sender_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_read: bool = False

    class Config:
        from_attributes = True


class AgendaItemBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    is_all_day: bool = False


class AgendaItemCreate(AgendaItemBase):
    event_id: str


class AgendaItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    is_all_day: Optional[bool] = None


class AgendaItem(AgendaItemBase):
    id: str
    event_id: str
    creator_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserLocationBase(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None


class UserLocationCreate(UserLocationBase):
    event_id: Optional[str] = None


class UserLocation(UserLocationBase):
    id: str
    user_id: str
    event_id: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class VideoCallBase(BaseModel):
    event_id: Optional[str] = None
    participants: List[str] = []
    is_group_call: bool = True


class VideoCallCreate(VideoCallBase):
    pass


class VideoCall(VideoCallBase):
    id: str
    creator_id: str
    is_active: bool = True
    started_at: datetime
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None


# Response models
class EventWithParticipants(Event):
    participants: List[User] = []
    agenda_items: List[AgendaItem] = []


class MessageWithSender(Message):
    sender: Optional[User] = None


class EventInviteResponse(BaseModel):
    success: bool
    message: str
    event: Optional[Event] = None


# Event Invitation Models
class EventInvitationBase(BaseModel):
    event_id: str
    invitee_id: str
    message: Optional[str] = None


class EventInvitationCreate(EventInvitationBase):
    pass


class EventInvitation(EventInvitationBase):
    id: str
    inviter_id: str
    status: str = "pending"  # pending, accepted, declined
    created_at: datetime
    responded_at: Optional[datetime] = None
    inviter: Optional[User] = None
    invitee: Optional[User] = None
    event: Optional[Event] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class InvitationResponse(BaseModel):
    invitation_id: str
    response: str  # "accepted" or "declined"


class EventParticipants(BaseModel):
    participants: List[User]
    invitations: List[EventInvitation]


# Event Map Pin Models
class PinType(str, Enum):
    LOCATION = "location"
    MEETING_POINT = "meeting_point"
    LANDMARK = "landmark"
    CUSTOM = "custom"


class EventPinBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    pin_type: PinType = PinType.LOCATION
    color: str = Field(default="#FF0000", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str = Field(default="pin", max_length=50)
    is_public: bool = True


class EventPinCreate(EventPinBase):
    event_id: str


class EventPinUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    pin_type: Optional[PinType] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    is_public: Optional[bool] = None


class EventPin(EventPinBase):
    id: str
    event_id: str
    creator_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EventPinWithCreator(EventPin):
    creator: Optional[User] = None
