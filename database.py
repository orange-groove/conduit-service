from supabase import create_client, Client
from config import settings
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime


class SupabaseClient:
    def __init__(self):
        # Use the configured key (should be service role key for server operations)
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_key
        )
    
    async def create_user(self, email: str, password: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user with Supabase Auth"""
        try:
            # Check Auth for existing user first (authoritative)
            existing_auth_user = await self.get_auth_user_by_email(email)
            if existing_auth_user:
                return {
                    "success": False,
                    "message": "Email already registered"
                }
            
            # If Auth user doesn't exist but stale profile row exists, remove it
            existing_profile = await self.get_user_by_email(email)
            if existing_profile:
                try:
                    self.client.table("profiles").delete().eq("email", email).execute()
                except Exception as cleanup_err:
                    print(f"Warning: could not delete stale profile for {email}: {cleanup_err}")
            
            auth_response = self.client.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_data
            })
            
            if auth_response.user:
                # Ensure a matching profile exists (no reliance on DB triggers)
                try:
                    await asyncio.sleep(0.1)
                    # Build metadata payload and upsert
                    metadata_payload = {
                        "full_name": user_data.get("full_name"),
                        "avatar_url": user_data.get("avatar_url"),
                        "phone_number": user_data.get("phone_number"),
                        "role": user_data.get("role", "user"),
                        "is_active": user_data.get("is_active", True),
                    }
                    await self.ensure_user_profile(auth_response.user)
                    # Apply any additional metadata updates on top
                    metadata_updates = {k: v for k, v in metadata_payload.items() if v is not None}
                    if metadata_updates:
                        self.client.table("profiles").update(metadata_updates).eq("id", auth_response.user.id).execute()
                except Exception as profile_error:
                    print(f"Warning: Could not ensure/update profile: {profile_error}")
                
                return {
                    "success": True,
                    "user": auth_response.user,
                    "message": "User created successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to create user"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error creating user: {str(e)}"
            }

    async def get_auth_user_by_email(self, email: str) -> Optional[Any]:
        """Find a Supabase Auth user by email using admin list."""
        try:
            result = self.client.auth.admin.list_users({"per_page": 200})
            for user in getattr(result, "users", []) or []:
                if getattr(user, "email", None) == email:
                    return user
            return None
        except Exception as e:
            print(f"Error listing auth users: {e}")
            return None
    
    async def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user with Supabase Auth"""
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                print(f"✅ Database: Supabase auth successful for user: {response.user.id}")
                return {
                    "success": True,
                    "user": response.user,
                    "session": response.session,
                    "message": "Authentication successful"
                }
            else:
                print(f"❌ Database: No user returned from Supabase")
                return {
                    "success": False,
                    "message": "Invalid credentials"
                }
        except Exception as e:
            print(f"💥 Database: Exception during auth: {str(e)}")
            print(f"💥 Database: Exception type: {type(e)}")
            return {
                "success": False,
                "message": f"Authentication error: {str(e)}"
            }
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile from database"""
        try:
            response = self.client.table("profiles").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching user profile: {e}")
            return None

    async def ensure_user_profile(self, user: Any) -> Optional[Dict[str, Any]]:
        """Ensure a profile row exists for the given Supabase auth user.

        If the row exists, update it from user metadata; otherwise, insert it.
        Returns the ensured row.
        """
        try:
            print(f"🔧 Ensuring profile for user: {user.id}")
            profile_payload: Dict[str, Any] = {
                "id": user.id,
                "email": getattr(user, "email", None),
                "full_name": (user.user_metadata or {}).get("full_name") or "",
                "avatar_url": (user.user_metadata or {}).get("avatar_url"),
                "phone_number": (user.user_metadata or {}).get("phone_number"),
                "role": (user.user_metadata or {}).get("role") or "user",
                "is_active": (user.user_metadata or {}).get("is_active", True),
            }
            print(f"🔧 Profile payload: {profile_payload}")

            # Check if profile exists
            existing = self.client.table("profiles").select("*").eq("id", user.id).execute()
            print(f"🔧 Existing profile check: {existing.data}")
            
            if existing.data:
                # Update existing
                print(f"🔧 Updating existing profile")
                self.client.table("profiles").update(profile_payload).eq("id", user.id).execute()
                return existing.data[0] | {k: v for k, v in profile_payload.items() if v is not None}
            else:
                # Insert new
                print(f"🔧 Inserting new profile")
                inserted = self.client.table("profiles").insert(profile_payload).execute()
                print(f"🔧 Insert result: {inserted.data}")
                if inserted.data:
                    return inserted.data[0]
                # Fallback: try to read back once
                print(f"🔧 Fallback: reading back profile")
                fetched = self.client.table("profiles").select("*").eq("id", user.id).execute()
                print(f"🔧 Fallback result: {fetched.data}")
                return fetched.data[0] if fetched.data else None
        except Exception as e:
            print(f"Error ensuring user profile: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user profile by email"""
        try:
            response = self.client.table("profiles").select("*").eq("email", email).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching user by email: {e}")
            return None
    
    async def update_user_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user profile"""
        try:
            self.client.table("profiles").update(updates).eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Error updating user profile: {e}")
            return False
    
    async def create_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new event"""
        try:
            response = self.client.table("events").insert(event_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating event: {e}")
            return None
    
    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get event by ID"""
        try:
            response = self.client.table("events").select("*").eq("id", event_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching event: {e}")
            return None
    
    async def get_user_events(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all events for a user with accurate participant counts"""
        try:
            # First get the user's event IDs
            user_events_response = self.client.table("user_events").select("event_id").eq("user_id", user_id).eq("is_active", True).execute()
            
            if not user_events_response.data:
                return []
            
            # Extract event IDs
            event_ids = [ue["event_id"] for ue in user_events_response.data]
            
            # Get the actual events
            events_response = self.client.table("events").select("*").in_("id", event_ids).execute()
            
            if not events_response.data:
                return []
            
            # For each event, get the actual participant count
            events_with_counts = []
            for event in events_response.data:
                try:
                    # Get actual participant count
                    participants_response = self.client.table("user_events").select("user_id").eq("event_id", event["id"]).eq("is_active", True).execute()
                    actual_count = len(participants_response.data) if participants_response.data else 0
                    
                    # Update the event with accurate count
                    event["participant_count"] = actual_count
                    events_with_counts.append(event)
                except Exception as e:
                    print(f"Error getting participant count for event {event.get('id', 'unknown')}: {e}")
                    # Use stored count as fallback
                    events_with_counts.append(event)
            
            return events_with_counts
        except Exception as e:
            print(f"Error fetching user events: {e}")
            return []
    
    async def join_event(self, user_id: str, event_id: str, role: str = "participant") -> bool:
        """Add user to event"""
        try:
            user_event_data = {
                "user_id": user_id,
                "event_id": event_id,
                "role": role,
                "is_active": True
            }
            self.client.table("user_events").insert(user_event_data).execute()
            
            # Note: Users are NOT automatically added to video calls
            # Video calls are created/joined on-demand when users click "Join Video"
            
            return True
        except Exception as e:
            print(f"Error joining event: {e}")
            return False
    
    async def leave_event(self, user_id: str, event_id: str) -> bool:
        """Remove user from event"""
        try:
            self.client.table("user_events").update({"is_active": False}).eq("user_id", user_id).eq("event_id", event_id).execute()
            
            # Note: Users are NOT automatically removed from video calls
            # They can still participate in video calls even if they leave the event
            # Video call management is separate from event participation
            
            return True
        except Exception as e:
            print(f"Error leaving event: {e}")
            return False
    
    async def send_message(self, message_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send a message"""
        try:
            response = self.client.table("messages").insert(message_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    async def get_event_messages(self, event_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get messages for an event"""
        try:
            response = self.client.table("messages").select("""
                *,
                sender:sender_id (id, full_name, avatar_url)
            """).eq("event_id", event_id).order("created_at", desc=False).limit(limit).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching event messages: {e}")
            return []
    
    async def get_direct_messages(self, user_id: str, other_user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get direct messages between two users"""
        try:
            # Use the correct Supabase syntax for OR conditions
            response = self.client.table("messages").select("""
                *,
                sender:sender_id (id, full_name, avatar_url)
            """).or_(f"and(sender_id.eq.{user_id},recipient_id.eq.{other_user_id}),and(sender_id.eq.{other_user_id},recipient_id.eq.{user_id})").order("created_at", desc=False).limit(limit).execute()
            return response.data or []
        except Exception as e:
            print(f"Error with direct messages query, trying manual approach: {e}")
            # Fallback: fetch messages in both directions and combine
            try:
                # Messages from user_id to other_user_id
                messages_1 = self.client.table("messages").select("""
                    *,
                    sender:sender_id (id, full_name, avatar_url)
                """).eq("sender_id", user_id).eq("recipient_id", other_user_id).order("created_at", desc=False).limit(limit).execute()
                
                # Messages from other_user_id to user_id
                messages_2 = self.client.table("messages").select("""
                    *,
                    sender:sender_id (id, full_name, avatar_url)
                """).eq("sender_id", other_user_id).eq("recipient_id", user_id).order("created_at", desc=False).limit(limit).execute()
                
                # Combine and sort by created_at (oldest first)
                all_messages = (messages_1.data or []) + (messages_2.data or [])
                all_messages.sort(key=lambda x: x.get("created_at", ""), reverse=False)
                
                return all_messages[:limit]
            except Exception as fallback_error:
                print(f"Fallback direct messages query also failed: {fallback_error}")
                return []
    
    async def update_user_location(self, user_id: str, location_data: Dict[str, Any]) -> bool:
        """Update user's current location using UPSERT approach"""
        try:
            # Use UPSERT to update existing record or create new one
            response = self.client.table("user_current_locations").upsert({
                "user_id": user_id,
                "latitude": location_data["latitude"],
                "longitude": location_data["longitude"],
                "accuracy": location_data.get("accuracy"),
                "heading": location_data.get("heading"),
                "speed": location_data.get("speed"),
                "timestamp": location_data.get("timestamp", datetime.utcnow().isoformat()),
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            
            return True
        except Exception as e:
            print(f"Error updating location: {e}")
            return False
    
    async def get_user_current_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's current location"""
        try:
            response = self.client.table("user_current_locations").select("""
                *,
                user:user_id (id, full_name, avatar_url)
            """).eq("user_id", user_id).execute()
            
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting user location: {e}")
            return None

    async def get_event_locations(self, event_id: str) -> List[Dict[str, Any]]:
        """Get current locations of all event participants who have shared their location"""
        try:
            # Get all participants of the event
            participants = await self.get_event_participants(event_id)
            if not participants:
                return []
            
            participant_ids = [p["user_id"] for p in participants]
            
            # Get current locations for all participants who are sharing
            response = self.client.table("user_current_locations").select("""
                *,
                user:user_id (id, full_name, avatar_url)
            """).in_("user_id", participant_ids).eq("is_shared", True).execute()
            
            return response.data or []
        except Exception as e:
            print(f"Error getting event locations: {e}")
            return []

    async def set_location_sharing(self, user_id: str, is_shared: bool) -> bool:
        """Enable/disable location sharing for user"""
        try:
            self.client.table("user_current_locations").update({
                "is_shared": is_shared,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()
            
            return True
        except Exception as e:
            print(f"Error setting location sharing: {e}")
            return False

    async def get_event_participants_with_latest_location(self, event_id: str) -> List[Dict[str, Any]]:
        """Return all participants with their latest location (may be None).

        Shape: [{ user: {..profile..}, location: {..latest location..} | None }]
        """
        try:
            # 1) Fetch active participant user_ids (no nested join to avoid FK dependency)
            ue_resp = self.client.table("user_events").select("user_id").eq("event_id", event_id).eq("is_active", True).execute()
            user_ids = [row.get("user_id") for row in (ue_resp.data or []) if row.get("user_id")]
            if not user_ids:
                return []

            # 2) Fetch profiles in batch
            profiles_resp = self.client.table("profiles").select("id, email, full_name, avatar_url, phone_number, role, is_active, created_at, updated_at").in_(
                "id", user_ids
            ).execute()
            id_to_profile: Dict[str, Dict[str, Any]] = {p["id"]: p for p in (profiles_resp.data or [])}

            # 3) Fetch latest locations for these users (ordered desc), then take first per user
            loc_resp = self.client.table("user_locations").select("*"
            ).eq("event_id", event_id
            ).in_("user_id", user_ids
            ).order("timestamp", desc=True).execute()

            latest_by_user: Dict[str, Dict[str, Any]] = {}
            for loc in (loc_resp.data or []):
                uid = loc.get("user_id")
                if uid and uid not in latest_by_user:
                    latest_by_user[uid] = loc

            # 4) Merge profiles with latest locations; include users even if no location yet
            merged: List[Dict[str, Any]] = []
            for uid in user_ids:
                profile = id_to_profile.get(uid)
                if not profile:
                    # Skip users without a profile row
                    continue
                merged.append({
                    "user": profile,
                    "location": latest_by_user.get(uid) or None
                })

            return merged
        except Exception as e:
            print(f"Error fetching participants with latest location: {e}")
            return []
    
    async def create_agenda_item(self, agenda_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create agenda item for an event"""
        try:
            response = self.client.table("agenda_items").insert(agenda_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating agenda item: {e}")
            return None
    
    async def get_event_agenda(self, event_id: str) -> List[Dict[str, Any]]:
        """Get agenda items for an event with pin information"""
        try:
            response = self.client.table("agenda_items").select("""
                *,
                pin:pin_id (
                    id,
                    title,
                    description,
                    latitude,
                    longitude,
                    pin_type,
                    color,
                    icon
                )
            """).eq("event_id", event_id).order("start_time").execute()
            return response.data or []
        except Exception as e:
            return []

    async def get_agenda_item(self, agenda_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific agenda item by ID"""
        try:
            response = self.client.table("agenda_items").select("*").eq("id", agenda_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            return None

    async def delete_agenda_item(self, agenda_id: str) -> bool:
        """Delete an agenda item"""
        try:
            self.client.table("agenda_items").delete().eq("id", agenda_id).execute()
            return True
        except Exception as e:
            return False
    
    # Event Invitations
    async def create_event_invitation(self, invitation_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create an event invitation"""
        try:
            response = self.client.table("event_invitations").insert(invitation_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating event invitation: {e}")
            return None
    
    async def get_event_invitations(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all invitations for an event with full user data for inviter and invitee"""
        try:
            
            # Try different Supabase join syntaxes
            try:
                # Method 1: Using the standard foreign key syntax
                response = self.client.table("event_invitations").select("""
                    *,
                    inviter:inviter_id(
                        id, email, full_name, avatar_url, phone_number, 
                        role, is_active, last_seen, created_at, updated_at
                    ),
                    invitee:invitee_id(
                        id, email, full_name, avatar_url, phone_number, 
                        role, is_active, last_seen, created_at, updated_at
                    )
                """).eq("event_id", event_id).order("created_at", desc=True).execute()
                
                
                # Check if joins worked
                if response.data and all(inv.get("inviter") and inv.get("invitee") for inv in response.data):
                    print("✅ Method 1 worked!")
                    return response.data
                else:
                    print("❌ Method 1 failed, trying method 2...")
                    
            except Exception as e:
                print(f"❌ Method 1 error: {e}")
            
            # Method 2: Manual fetching (guaranteed to work)
            simple_response = self.client.table("event_invitations").select("*").eq("event_id", event_id).order("created_at", desc=True).execute()
            
            enriched_invitations = []
            for inv in simple_response.data or []:
                try:
                    # Fetch inviter data
                    inviter_data = None
                    if inv.get("inviter_id"):
                        inviter_response = self.client.table("profiles").select("*").eq("id", inv["inviter_id"]).execute()
                        if inviter_response.data:
                            inviter_data = inviter_response.data[0]
                        else:
                            print(f"❌ No inviter data found for ID: {inv['inviter_id']}")
                    
                    # Fetch invitee data
                    invitee_data = None
                    if inv.get("invitee_id"):
                        invitee_response = self.client.table("profiles").select("*").eq("id", inv["invitee_id"]).execute()
                        if invitee_response.data:
                            invitee_data = invitee_response.data[0]
                        else:
                            print(f"❌ No invitee data found for ID: {inv['invitee_id']}")
                    
                    # Combine the data
                    enriched_invitation = inv.copy()
                    enriched_invitation["inviter"] = inviter_data
                    enriched_invitation["invitee"] = invitee_data
                    enriched_invitations.append(enriched_invitation)
                    
                except Exception as e:
                    print(f"Error enriching invitation {inv.get('id')}: {e}")
                    enriched_invitations.append(inv)
            
            return enriched_invitations
            
        except Exception as e:
            print(f"❌ All methods failed: {e}")
            return []
    
    async def get_user_invitations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all pending invitations for a user with full inviter and event details"""
        try:
            response = self.client.table("event_invitations").select("""
                *,
                inviter:inviter_id (id, full_name, email, avatar_url),
                invitee:invitee_id (id, full_name, email, avatar_url),
                event:event_id (id, title, start_date, end_date, location, is_private)
            """).eq("invitee_id", user_id).eq("status", "pending").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching user invitations: {e}")
            return []
    
    async def respond_to_invitation(self, invitation_id: str, user_id: str, response: str) -> bool:
        """Respond to an event invitation (accept/decline)"""
        try:
            # Update invitation status
            self.client.table("event_invitations").update({
                "status": response,
                "responded_at": "now()"
            }).eq("id", invitation_id).eq("invitee_id", user_id).execute()
            
            # If accepted, add user to event
            if response == "accepted":
                # Get invitation details
                invitation = self.client.table("event_invitations").select("event_id").eq("id", invitation_id).execute()
                if invitation.data:
                    event_id = invitation.data[0]["event_id"]
                    
                    # Check if user is already in the event
                    existing_check = self.client.table("user_events").select("user_id").eq("event_id", event_id).eq("user_id", user_id).eq("is_active", True).execute()
                    
                    if not existing_check.data:
                        # User not in event, add them
                        await self.join_event(user_id, event_id, "participant")
                        # Note: User is NOT automatically added to video calls
                        # They must manually join video calls when ready
            
            return True
        except Exception as e:
            print(f"Error responding to invitation: {e}")
            return False
    
    async def get_event_participants(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all participants in an event with full profile data"""
        try:
            response = self.client.table("user_events").select("""
                *,
                user:user_id (
                    id, email, full_name, avatar_url, phone_number, 
                    role, is_active, last_seen, created_at, updated_at
                )
            """).eq("event_id", event_id).eq("is_active", True).execute()
            
            return response.data or []
        except Exception as e:
            print(f"Error fetching event participants: {e}")
            return []
    
    # User Search
    async def search_users(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by email or name"""
        try:
            # Search by email or full_name using ilike (case-insensitive)
            # Use the correct Supabase syntax for OR conditions
            response = self.client.table("profiles").select("""
                id, email, full_name, avatar_url, phone_number, is_active, created_at
            """).or_(f"email.ilike.%{query}%,full_name.ilike.%{query}%").eq("is_active", True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            print(f"Error searching users: {e}")
            # Fallback: try separate queries and combine results
            try:
                email_results = self.client.table("profiles").select("""
                    id, email, full_name, avatar_url, phone_number, is_active, created_at
                """).ilike("email", f"%{query}%").eq("is_active", True).limit(limit).execute()
                
                name_results = self.client.table("profiles").select("""
                    id, email, full_name, avatar_url, phone_number, is_active, created_at
                """).ilike("full_name", f"%{query}%").eq("is_active", True).limit(limit).execute()
                
                # Combine and deduplicate results
                all_results = (email_results.data or []) + (name_results.data or [])
                seen_ids = set()
                unique_results = []
                for user in all_results:
                    if user["id"] not in seen_ids:
                        seen_ids.add(user["id"])
                        unique_results.append(user)
                        if len(unique_results) >= limit:
                            break
                
                return unique_results
            except Exception as fallback_error:
                print(f"Fallback search also failed: {fallback_error}")
                return []
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by exact email match"""
        try:
            response = self.client.table("profiles").select("""
                id, email, full_name, avatar_url, phone_number, is_active, created_at
            """).eq("email", email).eq("is_active", True).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching user by email: {e}")
            return None
    
    # Video Call Methods
    async def create_video_call(self, call_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new video call"""
        try:
            response = self.client.table("video_calls").insert(call_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating video call: {e}")
            return None
    
    async def get_video_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get video call by ID"""
        try:
            response = self.client.table("video_calls").select("*").eq("id", call_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching video call: {e}")
            return None
    
    async def update_video_call(self, call_id: str, updates: Dict[str, Any]) -> bool:
        """Update video call"""
        try:
            self.client.table("video_calls").update(updates).eq("id", call_id).execute()
            return True
        except Exception as e:
            print(f"Error updating video call: {e}")
            return False
    
    async def get_user_active_calls(self, user_id: str) -> List[Dict[str, Any]]:
        """Get active video calls for a user"""
        try:
            response = self.client.table("video_calls").select("*").or_(
                f"creator_id.eq.{user_id},participants.cs.[{user_id}]"
            ).eq("is_active", True).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching user active calls: {e}")
            return []
    
    # Event Pin Methods
    async def create_event_pin(self, pin_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new event pin"""
        try:
            response = self.client.table("event_pins").insert(pin_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error creating event pin: {e}")
            return None
    
    async def get_event_pins(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all pins for an event"""
        try:
            response = self.client.table("event_pins").select("""
                *,
                creator:creator_id (id, full_name, avatar_url)
            """).eq("event_id", event_id).order("created_at", desc=False).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching event pins: {e}")
            return []
    
    async def get_event_pin(self, pin_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific event pin"""
        try:
            response = self.client.table("event_pins").select("""
                *,
                creator:creator_id (id, full_name, avatar_url)
            """).eq("id", pin_id).single().execute()
            return response.data if response.data else None
        except Exception as e:
            print(f"Error fetching event pin: {e}")
            return None
    
    async def update_event_pin(self, pin_id: str, updates: Dict[str, Any]) -> bool:
        """Update an event pin"""
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            self.client.table("event_pins").update(updates).eq("id", pin_id).execute()
            return True
        except Exception as e:
            print(f"Error updating event pin: {e}")
            return False
    
    async def delete_event_pin(self, pin_id: str) -> bool:
        """Delete an event pin"""
        try:
            self.client.table("event_pins").delete().eq("id", pin_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting event pin: {e}")
            return False
    
    async def get_pins_by_type(self, event_id: str, pin_type: str) -> List[Dict[str, Any]]:
        """Get pins of a specific type for an event"""
        try:
            response = self.client.table("event_pins").select("""
                *,
                creator:creator_id (id, full_name, avatar_url)
            """).eq("event_id", event_id).eq("pin_type", pin_type).order("created_at", desc=False).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching pins by type: {e}")
            return []
    
    async def get_pins_in_bounds(self, event_id: str, north: float, south: float, east: float, west: float) -> List[Dict[str, Any]]:
        """Get pins within geographic bounds"""
        try:
            response = self.client.table("event_pins").select("""
                *,
                creator:creator_id (id, full_name, avatar_url)
            """).eq("event_id", event_id).gte("latitude", south).lte("latitude", north).gte("longitude", west).lte("longitude", east).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching pins in bounds: {e}")
            return []

    async def search_event_pins(self, event_id: str, query: str) -> List[Dict[str, Any]]:
        """Search pins by title and description"""
        try:
            # Search in title and description fields
            response = self.client.table("event_pins").select("""
                *,
                creator:creator_id (id, full_name, avatar_url)
            """).eq("event_id", event_id).or_(f"title.ilike.%{query}%,description.ilike.%{query}%").execute()
            return response.data or []
        except Exception as e:
            return []
    
    async def ensure_event_video_call(self, event_id: str, creator_id: str) -> Optional[Dict[str, Any]]:
        """Ensure a video call exists for an event, create one if it doesn't"""
        try:
            # Check if video call already exists
            response = self.client.table("video_calls").select("*").eq("event_id", event_id).execute()
            
            if response.data:
                # Video call exists, return it
                return response.data[0]
            else:
                # Create new video call
                video_call_data = {
                    "id": str(uuid.uuid4()),
                    "event_id": event_id,
                    "creator_id": creator_id,
                    "participants": [creator_id],
                    "is_group_call": True,
                    "is_active": True,
                    "started_at": datetime.utcnow().isoformat()
                }
                return await self.create_video_call(video_call_data)
        except Exception as e:
            print(f"Error ensuring video call for event {event_id}: {e}")
            return None


# Global database instance
db = SupabaseClient()
