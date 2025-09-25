# Conduit - Social Event & Location Sharing API

Conduit is a FastAPI-based backend service for a social event and location sharing app, similar to Life 360 but with enhanced social features for friends and families during events and vacations.

## Features

- **User Authentication**: Secure user registration and authentication using Supabase Auth
- **Event Management**: Create, join, and manage events with participants
- **Real-time Messaging**: WebSocket-based messaging for events and direct messages
- **Video Chat**: WebRTC-based video calling for groups and individuals
- **Location Tracking**: Real-time location sharing and mapping for event participants
- **Agenda & Calendar**: Create and manage event agendas with calendar views

## Tech Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **Supabase**: Backend-as-a-Service for database, authentication, and real-time features
- **WebSockets**: Real-time communication for messaging and video chat signaling
- **PostgreSQL**: Database (via Supabase)
- **JWT**: Token-based authentication

## Quick Start

### Prerequisites

- Python 3.8+
- Supabase account and project
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd conduit-service
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Supabase**
   - Create a new Supabase project at https://supabase.com
   - Copy the database schema from `database_schema.sql` and run it in your Supabase SQL editor
   - Get your project URL and API keys from the Supabase dashboard

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` file with your Supabase credentials:
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your_anon_key_here
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
   SECRET_KEY=your_super_secret_key_change_this_in_production
   ```

6. **Run the application**
   ```bash
   python main.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Access the API**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register a new user
- `POST /api/v1/auth/login` - Login user
- `GET /api/v1/auth/me` - Get current user profile
- `PUT /api/v1/auth/me` - Update user profile

### Events
- `POST /api/v1/events/` - Create new event
- `GET /api/v1/events/` - Get user's events
- `GET /api/v1/events/{event_id}` - Get event details
- `PUT /api/v1/events/{event_id}` - Update event
- `POST /api/v1/events/{event_id}/join` - Join event
- `POST /api/v1/events/{event_id}/leave` - Leave event

### Messaging
- `WebSocket /api/v1/messages/ws/{user_id}` - WebSocket connection for real-time messaging
- `POST /api/v1/messages/` - Send message (HTTP fallback)
- `GET /api/v1/messages/events/{event_id}` - Get event messages
- `GET /api/v1/messages/direct/{user_id}` - Get direct messages

### Location
- `POST /api/v1/location/update` - Update user location
- `GET /api/v1/location/event/{event_id}` - Get event participants' locations

### Video Chat
- `WebSocket /api/v1/video/ws/{call_id}/{user_id}` - WebSocket for video chat signaling
- `POST /api/v1/video/` - Create video call
- `GET /api/v1/video/{call_id}` - Get video call details
- `POST /api/v1/video/{call_id}/join` - Join video call
- `POST /api/v1/video/{call_id}/leave` - Leave video call

### Agenda
- `POST /api/v1/agenda/` - Create agenda item
- `GET /api/v1/agenda/event/{event_id}` - Get event agenda
- `GET /api/v1/agenda/user/calendar` - Get user's calendar view
- `PUT /api/v1/agenda/{agenda_id}` - Update agenda item

## Database Schema

The application uses the following main tables:

- **profiles**: User profiles (extends Supabase auth.users)
- **events**: Event information
- **user_events**: User-event relationships
- **messages**: Chat messages
- **user_locations**: Location tracking data
- **agenda_items**: Event agenda items
- **video_calls**: Video call sessions

See `database_schema.sql` for the complete schema with indexes and Row Level Security policies.

## WebSocket Usage

### Real-time Messaging
Connect to `/api/v1/messages/ws/{user_id}` and send JSON messages:

```javascript
// Send a message
{
  "type": "send_message",
  "content": "Hello everyone!",
  "message_type": "text",
  "event_id": "event-uuid"
}
```

### Video Chat Signaling
Connect to `/api/v1/video/ws/{call_id}/{user_id}` for WebRTC signaling:

```javascript
// Send WebRTC offer
{
  "type": "offer",
  "offer": { /* WebRTC offer object */ },
  "target_user": "target-user-id"
}
```

## Security

- **JWT Authentication**: All protected endpoints require valid JWT tokens
- **Row Level Security**: Database-level security using Supabase RLS
- **CORS**: Configurable CORS settings for web clients
- **Input Validation**: Pydantic models for request/response validation

## Development

### Project Structure
```
conduit-service/
├── main.py                 # FastAPI application entry point
├── config.py              # Configuration settings
├── models.py              # Pydantic models
├── database.py            # Supabase client and database operations
├── auth.py                # Authentication utilities
├── routers/               # API route handlers
│   ├── auth_router.py
│   ├── events_router.py
│   ├── messaging_router.py
│   ├── location_router.py
│   ├── video_router.py
│   └── agenda_router.py
├── database_schema.sql    # Database schema for Supabase
├── requirements.txt       # Python dependencies
└── README.md
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests (when test files are created)
pytest
```

### Code Quality
```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

## Deployment

### Environment Variables for Production
- Set `DEBUG=False`
- Use strong `SECRET_KEY`
- Configure proper `ALLOWED_ORIGINS`
- Set up proper logging

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please open an issue in the repository.
