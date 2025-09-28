"""
Firebase Cloud Messaging service for push notifications.
"""

import json
import requests
from typing import List, Dict, Any, Optional
from config import settings
import logging

logger = logging.getLogger(__name__)

class FCMService:
    """Firebase Cloud Messaging service for sending push notifications"""
    
    def __init__(self):
        # Server key for legacy API (simpler approach)
        self.server_key = settings.fcm_server_key
        
        # FCM endpoints
        self.legacy_fcm_url = "https://fcm.googleapis.com/fcm/send"
        self.fcm_url = None  # Not using v1 API with server key approach
    
    async def send_notification_to_user(
        self, 
        user_id: str, 
        title: str, 
        body: str, 
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send notification to a specific user"""
        try:
            # Get user's device tokens from database
            device_tokens = await self._get_user_device_tokens(user_id)
            
            if not device_tokens:
                logger.warning(f"No device tokens found for user {user_id}")
                return False
            
            # Send to all user's devices
            success_count = 0
            for token in device_tokens:
                if await self._send_single_notification(token, title, body, data):
                    success_count += 1
            
            logger.info(f"✅ Sent notification to {success_count}/{len(device_tokens)} devices for user {user_id}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Failed to send notification to user {user_id}: {e}")
            return False
    
    async def send_message_notification(
        self, 
        recipient_id: str, 
        sender_name: str, 
        message_content: str,
        event_id: Optional[str] = None
    ) -> bool:
        """Send notification for a new message"""
        title = f"New message from {sender_name}"
        body = message_content[:100] + "..." if len(message_content) > 100 else message_content
        
        data = {
            "type": "message",
            "sender_name": sender_name,
            "event_id": event_id or "",
        }
        
        return await self.send_notification_to_user(recipient_id, title, body, data)
    
    async def send_video_call_notification(
        self, 
        recipient_id: str, 
        caller_name: str,
        event_id: Optional[str] = None
    ) -> bool:
        """Send notification for a video call"""
        title = f"Video call from {caller_name}"
        body = f"{caller_name} is starting a video call"
        
        data = {
            "type": "video_call",
            "caller_name": caller_name,
            "event_id": event_id or "",
        }
        
        return await self.send_notification_to_user(recipient_id, title, body, data)
    
    async def _send_single_notification(
        self, 
        token: str, 
        title: str, 
        body: str, 
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send notification to a single device token"""
        try:
            # Use legacy API with server key
            if self.server_key:
                return await self._send_legacy_notification(token, title, body, data)
            else:
                logger.warning("No FCM server key found. Please set FCM_SERVER_KEY in your .env file.")
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to send notification to token {token[:10]}...: {e}")
            return False
    
    async def _send_v1_notification(
        self, 
        token: str, 
        title: str, 
        body: str, 
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send notification using FCM v1 API"""
        try:
            if not self.project_id or not self.private_key or not self.client_email:
                logger.warning("FCM v1 API not configured, skipping")
                return False
            
            # Get access token
            access_token = await self._get_access_token()
            if not access_token:
                return False
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "message": {
                    "token": token,
                    "notification": {
                        "title": title,
                        "body": body
                    },
                    "data": data or {}
                }
            }
            
            response = requests.post(self.fcm_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                logger.info(f"✅ FCM v1: Notification sent successfully")
                return True
            else:
                logger.error(f"❌ FCM v1 failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ FCM v1 error: {e}")
            return False
    
    async def _send_legacy_notification(
        self, 
        token: str, 
        title: str, 
        body: str, 
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send notification using legacy FCM API"""
        try:
            if not self.server_key:
                logger.warning("FCM server key not configured")
                return False
            
            headers = {
                'Authorization': f'key={self.server_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "to": token,
                "notification": {
                    "title": title,
                    "body": body
                },
                "data": data or {}
            }
            
            response = requests.post(self.legacy_fcm_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success', 0) > 0:
                    logger.info(f"✅ Legacy FCM: Notification sent successfully")
                    return True
                else:
                    logger.error(f"❌ Legacy FCM failed: {result}")
                    return False
            else:
                logger.error(f"❌ Legacy FCM failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Legacy FCM error: {e}")
            return False
    
    async def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token for FCM v1 API"""
        try:
            import jwt
            import time
            
            now = int(time.time())
            payload = {
                'iss': self.client_email,
                'sub': self.client_email,
                'aud': 'https://oauth2.googleapis.com/token',
                'iat': now,
                'exp': now + 3600,
                'scope': 'https://www.googleapis.com/auth/firebase.messaging'
            }
            
            # Create JWT token
            token = jwt.encode(payload, self.private_key, algorithm='RS256')
            
            # Exchange for access token
            response = requests.post('https://oauth2.googleapis.com/token', data={
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': token
            })
            
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                logger.error(f"❌ Failed to get access token: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting access token: {e}")
            return None
    
    async def _get_user_device_tokens(self, user_id: str) -> List[str]:
        """Get device tokens for a user from database"""
        try:
            from database import db
            response = db.client.table("user_device_tokens").select("token").eq("user_id", user_id).eq("is_active", True).execute()
            return [token["token"] for token in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting device tokens for user {user_id}: {e}")
            return []

# Global FCM service instance
fcm_service = FCMService()
