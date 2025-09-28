"""
Push notification endpoints for device token management and FCM integration.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from auth import get_current_active_user
from models import User
from database import db
from fcm_service import fcm_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class DeviceTokenRequest(BaseModel):
    token: str = Field(..., min_length=1, description="FCM device token")
    device_type: str = Field(..., pattern="^(ios|android|web)$", description="Device type")
    device_name: Optional[str] = Field(None, max_length=100, description="Device name")


class NotificationResponse(BaseModel):
    success: bool
    message: str


@router.post("/register-token", response_model=NotificationResponse)
async def register_device_token(
    request: DeviceTokenRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Register a device token for push notifications"""
    try:
        success = await db.register_device_token(
            user_id=current_user.id,
            token=request.token,
            device_type=request.device_type,
            device_name=request.device_name
        )
        
        if success:
            return NotificationResponse(
                success=True,
                message="Device token registered successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to register device token"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error registering device token: {str(e)}"
        )


@router.post("/unregister-token", response_model=NotificationResponse)
async def unregister_device_token(
    request: DeviceTokenRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Unregister a device token"""
    try:
        success = await db.unregister_device_token(
            user_id=current_user.id,
            token=request.token
        )
        
        if success:
            return NotificationResponse(
                success=True,
                message="Device token unregistered successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to unregister device token"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error unregistering device token: {str(e)}"
        )


@router.get("/test")
async def test_notification(
    current_user: User = Depends(get_current_active_user)
):
    """Send a test notification to the current user"""
    try:
        success = await fcm_service.send_notification_to_user(
            user_id=current_user.id,
            title="Test Notification",
            body="This is a test notification from Conduit!",
            data={"type": "test"}
        )
        
        if success:
            return {"message": "Test notification sent successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to send test notification"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending test notification: {str(e)}"
        )
