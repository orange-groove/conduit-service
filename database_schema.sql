-- Conduit Database Schema for Supabase
-- Run these SQL commands in your Supabase SQL editor

-- Enable RLS (Row Level Security)
-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users profiles table (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    avatar_url TEXT,
    phone_number TEXT,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_seen TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    creator_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL CHECK (LENGTH(title) <= 200),
    description TEXT,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE,
    location TEXT,
    location_coords JSONB, -- {latitude: number, longitude: number, accuracy?: number}
    is_private BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
    participant_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- User-Event relationship table
CREATE TABLE IF NOT EXISTS user_events (
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'participant' CHECK (role IN ('creator', 'admin', 'participant')),
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, event_id)
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    sender_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'image', 'location', 'system')),
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    recipient_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    metadata JSONB, -- Additional data for different message types
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT message_target_check CHECK (
        (event_id IS NOT NULL AND recipient_id IS NULL) OR 
        (event_id IS NULL AND recipient_id IS NOT NULL)
    )
);

-- User locations table
-- OLD TABLE (for migration reference)
-- CREATE TABLE IF NOT EXISTS user_locations (
--     id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
--     user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
--     event_id UUID REFERENCES events(id) ON DELETE SET NULL,
--     latitude DECIMAL(10, 8) NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
--     longitude DECIMAL(11, 8) NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
--     accuracy DECIMAL(10, 2),
--     heading DECIMAL(5, 2),
--     speed DECIMAL(8, 2),
--     timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
-- );

-- NEW OPTIMIZED TABLE: Single record per user
CREATE TABLE IF NOT EXISTS user_current_locations (
    user_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    latitude DECIMAL(10, 8) NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
    longitude DECIMAL(11, 8) NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
    accuracy DECIMAL(10, 2),
    heading DECIMAL(5, 2),
    speed DECIMAL(8, 2),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_shared BOOLEAN DEFAULT false,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agenda items table
CREATE TABLE IF NOT EXISTS agenda_items (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    creator_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL CHECK (LENGTH(title) <= 200),
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    pin_id UUID REFERENCES event_pins(id) ON DELETE SET NULL,
    is_all_day BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Video calls table
CREATE TABLE IF NOT EXISTS video_calls (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    creator_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    participants UUID[] NOT NULL DEFAULT '{}',
    is_group_call BOOLEAN NOT NULL DEFAULT true,
    is_active BOOLEAN NOT NULL DEFAULT true,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE
);

-- Event invitations table
CREATE TABLE IF NOT EXISTS event_invitations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    inviter_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    invitee_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(event_id, invitee_id)
);

-- Event map pins table
CREATE TABLE IF NOT EXISTS event_pins (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE NOT NULL,
    creator_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL CHECK (LENGTH(title) <= 100),
    description TEXT,
    latitude DECIMAL(10, 8) NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
    longitude DECIMAL(11, 8) NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
    pin_type TEXT NOT NULL DEFAULT 'location' CHECK (pin_type IN ('location', 'meeting_point', 'landmark', 'custom')),
    color TEXT DEFAULT '#FF0000' CHECK (LENGTH(color) = 7 AND color LIKE '#%'),
    icon TEXT DEFAULT 'pin',
    is_public BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_events_creator_id ON events(creator_id);
CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events(user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_event_id ON user_events(event_id);
CREATE INDEX IF NOT EXISTS idx_user_events_active ON user_events(is_active);

CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_event_id ON messages(event_id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient_id ON messages(recipient_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

-- OLD INDEXES (for migration reference)
-- CREATE INDEX IF NOT EXISTS idx_user_locations_user_id ON user_locations(user_id);
-- CREATE INDEX IF NOT EXISTS idx_user_locations_event_id ON user_locations(event_id);
-- CREATE INDEX IF NOT EXISTS idx_user_locations_timestamp ON user_locations(timestamp);

-- NEW INDEXES for optimized table
CREATE INDEX IF NOT EXISTS idx_user_current_locations_shared ON user_current_locations(is_shared) WHERE is_shared = true;
CREATE INDEX IF NOT EXISTS idx_user_current_locations_timestamp ON user_current_locations(timestamp);

CREATE INDEX IF NOT EXISTS idx_agenda_items_event_id ON agenda_items(event_id);
CREATE INDEX IF NOT EXISTS idx_agenda_items_start_time ON agenda_items(start_time);

CREATE INDEX IF NOT EXISTS idx_video_calls_creator_id ON video_calls(creator_id);
CREATE INDEX IF NOT EXISTS idx_video_calls_event_id ON video_calls(event_id);
CREATE INDEX IF NOT EXISTS idx_video_calls_active ON video_calls(is_active);

-- Event pins indexes
CREATE INDEX IF NOT EXISTS idx_event_pins_event_id ON event_pins(event_id);
CREATE INDEX IF NOT EXISTS idx_event_pins_creator_id ON event_pins(creator_id);
CREATE INDEX IF NOT EXISTS idx_event_pins_location ON event_pins(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_event_pins_pin_type ON event_pins(pin_type);

-- Row Level Security (RLS) Policies

-- Profiles policies
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public profiles are viewable by everyone" ON profiles;
CREATE POLICY "Public profiles are viewable by everyone" ON profiles
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can insert their own profile" ON profiles;
CREATE POLICY "Users can insert their own profile" ON profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON profiles;
CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);

-- Events policies
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Events are viewable by participants" ON events;
CREATE POLICY "Events are viewable by participants" ON events
    FOR SELECT USING (
        NOT is_private OR 
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = events.id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )
    );

DROP POLICY IF EXISTS "Users can create events" ON events;
CREATE POLICY "Users can create events" ON events
    FOR INSERT WITH CHECK (auth.uid() = creator_id);

DROP POLICY IF EXISTS "Event creators can update their events" ON events;
CREATE POLICY "Event creators can update their events" ON events
    FOR UPDATE USING (auth.uid() = creator_id);

-- User events policies
ALTER TABLE user_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their event memberships" ON user_events;
CREATE POLICY "Users can view their event memberships" ON user_events
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can join events" ON user_events;
CREATE POLICY "Users can join events" ON user_events
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can leave events" ON user_events;
CREATE POLICY "Users can leave events" ON user_events
    FOR UPDATE USING (auth.uid() = user_id);

-- Messages policies
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view messages in their events" ON messages;
CREATE POLICY "Users can view messages in their events" ON messages
    FOR SELECT USING (
        (event_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = messages.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )) OR
        (recipient_id IS NOT NULL AND (auth.uid() = sender_id OR auth.uid() = recipient_id))
    );

DROP POLICY IF EXISTS "Users can send messages" ON messages;
CREATE POLICY "Users can send messages" ON messages
    FOR INSERT WITH CHECK (auth.uid() = sender_id);

-- OLD POLICIES (for migration reference)
-- ALTER TABLE user_locations ENABLE ROW LEVEL SECURITY;
-- DROP POLICY IF EXISTS "Users can view locations in their events" ON user_locations;
-- CREATE POLICY "Users can view locations in their events" ON user_locations
--     FOR SELECT USING (
--         auth.uid() = user_id OR
--         (event_id IS NOT NULL AND EXISTS (
--             SELECT 1 FROM user_events 
--             WHERE user_events.event_id = user_locations.event_id 
--             AND user_events.user_id = auth.uid()
--             AND user_events.is_active = true
--         ))
--     );
-- DROP POLICY IF EXISTS "Users can update their own location" ON user_locations;
-- CREATE POLICY "Users can update their own location" ON user_locations
--     FOR INSERT WITH CHECK (auth.uid() = user_id);

-- NEW POLICIES for optimized table
ALTER TABLE user_current_locations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view shared locations in their events" ON user_current_locations;
CREATE POLICY "Users can view shared locations in their events" ON user_current_locations
    FOR SELECT USING (
        auth.uid() = user_id OR
        (is_shared = true AND EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.user_id = auth.uid()
            AND user_events.is_active = true
            AND EXISTS (
                SELECT 1 FROM user_events ue2 
                WHERE ue2.event_id = user_events.event_id 
                AND ue2.user_id = user_current_locations.user_id
                AND ue2.is_active = true
            )
        ))
    );

DROP POLICY IF EXISTS "Users can update their own location" ON user_current_locations;
CREATE POLICY "Users can update their own location" ON user_current_locations
    FOR ALL USING (auth.uid() = user_id);

-- Agenda items policies
ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Event participants can view agenda items" ON agenda_items;
CREATE POLICY "Event participants can view agenda items" ON agenda_items
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = agenda_items.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )
    );

DROP POLICY IF EXISTS "Event participants can create agenda items" ON agenda_items;
CREATE POLICY "Event participants can create agenda items" ON agenda_items
    FOR INSERT WITH CHECK (
        auth.uid() = creator_id AND
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = agenda_items.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )
    );

DROP POLICY IF EXISTS "Agenda creators can update their items" ON agenda_items;
CREATE POLICY "Agenda creators can update their items" ON agenda_items
    FOR UPDATE USING (auth.uid() = creator_id);

-- Video calls policies
ALTER TABLE video_calls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Participants can view video calls" ON video_calls;
CREATE POLICY "Participants can view video calls" ON video_calls
    FOR SELECT USING (
        auth.uid() = creator_id OR 
        auth.uid() = ANY(participants) OR
        (event_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = video_calls.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        ))
    );

DROP POLICY IF EXISTS "Users can create video calls" ON video_calls;
CREATE POLICY "Users can create video calls" ON video_calls
    FOR INSERT WITH CHECK (auth.uid() = creator_id);

DROP POLICY IF EXISTS "Call creators can update calls" ON video_calls;
CREATE POLICY "Call creators can update calls" ON video_calls
    FOR UPDATE USING (auth.uid() = creator_id);

-- Event invitations policies
ALTER TABLE event_invitations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view invitations they sent or received" ON event_invitations;
CREATE POLICY "Users can view invitations they sent or received" ON event_invitations
    FOR SELECT USING (auth.uid() = inviter_id OR auth.uid() = invitee_id);

DROP POLICY IF EXISTS "Event participants can create invitations" ON event_invitations;
CREATE POLICY "Event participants can create invitations" ON event_invitations
    FOR INSERT WITH CHECK (
        auth.uid() = inviter_id AND
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_id = auth.uid() 
            AND event_id = event_invitations.event_id 
            AND is_active = true
        )
    );

DROP POLICY IF EXISTS "Invitees can respond to their invitations" ON event_invitations;
CREATE POLICY "Invitees can respond to their invitations" ON event_invitations
    FOR UPDATE USING (auth.uid() = invitee_id);

-- Event pins policies
ALTER TABLE event_pins ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Event participants can view pins" ON event_pins;
CREATE POLICY "Event participants can view pins" ON event_pins
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = event_pins.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )
    );

DROP POLICY IF EXISTS "Event participants can create pins" ON event_pins;
CREATE POLICY "Event participants can create pins" ON event_pins
    FOR INSERT WITH CHECK (
        auth.uid() = creator_id AND
        EXISTS (
            SELECT 1 FROM user_events 
            WHERE user_events.event_id = event_pins.event_id 
            AND user_events.user_id = auth.uid()
            AND user_events.is_active = true
        )
    );

DROP POLICY IF EXISTS "Pin creators can update their pins" ON event_pins;
CREATE POLICY "Pin creators can update their pins" ON event_pins
    FOR UPDATE USING (auth.uid() = creator_id);

DROP POLICY IF EXISTS "Pin creators can delete their pins" ON event_pins;
CREATE POLICY "Pin creators can delete their pins" ON event_pins
    FOR DELETE USING (auth.uid() = creator_id);

-- Functions for real-time subscriptions
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url, phone_number)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
        COALESCE(NEW.raw_user_meta_data->>'avatar_url', ''),
        COALESCE(NEW.raw_user_meta_data->>'phone_number', '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to automatically create profile when user signs up
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE handle_new_user();

-- Function to update participant count
CREATE OR REPLACE FUNCTION update_event_participant_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.is_active = true THEN
        UPDATE events 
        SET participant_count = participant_count + 1
        WHERE id = NEW.event_id;
    ELSIF TG_OP = 'UPDATE' AND OLD.is_active = true AND NEW.is_active = false THEN
        UPDATE events 
        SET participant_count = participant_count - 1
        WHERE id = NEW.event_id;
    ELSIF TG_OP = 'UPDATE' AND OLD.is_active = false AND NEW.is_active = true THEN
        UPDATE events 
        SET participant_count = participant_count + 1
        WHERE id = NEW.event_id;
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Trigger to update participant count
DROP TRIGGER IF EXISTS user_events_participant_count ON user_events;
CREATE TRIGGER user_events_participant_count
    AFTER INSERT OR UPDATE ON user_events
    FOR EACH ROW EXECUTE PROCEDURE update_event_participant_count();
