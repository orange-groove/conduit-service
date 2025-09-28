# Firebase Cloud Messaging (FCM) Setup Guide

This guide will help you set up Firebase Cloud Messaging for push notifications in your Conduit application.

## 1. Firebase Project Setup

### Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Create a project" or "Add project"
3. Enter project name: `conduit-notifications` (or your preferred name)
4. Enable Google Analytics (optional)
5. Click "Create project"

### Enable Cloud Messaging
1. In your Firebase project, go to "Build" → "Authentication"
2. Click "Get started" to enable Authentication
3. Go to "Build" → "Cloud Messaging"
4. The FCM service is automatically enabled

## 2. Generate Service Account Key

### Create Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your Firebase project
3. Go to "IAM & Admin" → "Service Accounts"
4. Click "Create Service Account"
5. Name: `conduit-fcm-service`
6. Description: `Service account for Conduit FCM notifications`
7. Click "Create and Continue"
8. Grant roles: "Firebase Cloud Messaging Admin"
9. Click "Done"

### Generate Key
1. Find your service account in the list
2. Click the three dots → "Manage keys"
3. Click "Add key" → "Create new key"
4. Choose "JSON" format
5. Download the key file (keep it secure!)

## 3. Environment Configuration

Add these variables to your `.env` file:

```env
# Firebase Configuration
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----"
FIREBASE_CLIENT_EMAIL=conduit-fcm-service@your-project.iam.gserviceaccount.com
FIREBASE_CREDENTIALS_PATH=/path/to/your/service-account-key.json
```

### Getting the Values

**FIREBASE_PROJECT_ID**: Found in Firebase Console → Project Settings → General

**FIREBASE_PRIVATE_KEY**: From your downloaded JSON file, copy the `private_key` value (including the quotes and newlines)

**FIREBASE_CLIENT_EMAIL**: From your downloaded JSON file, copy the `client_email` value

**FIREBASE_CREDENTIALS_PATH**: Path to your downloaded JSON file (alternative to individual keys)

## 4. Database Setup

Run the database schema update to add the device tokens table:

```sql
-- User device tokens for push notifications
CREATE TABLE IF NOT EXISTS user_device_tokens (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
    token TEXT NOT NULL UNIQUE,
    device_type TEXT NOT NULL CHECK (device_type IN ('ios', 'android', 'web')),
    device_name TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RLS Policies for user_device_tokens
DROP POLICY IF EXISTS "Users can view their own device tokens" ON user_device_tokens;
CREATE POLICY "Users can view their own device tokens" ON user_device_tokens
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own device tokens" ON user_device_tokens;
CREATE POLICY "Users can insert their own device tokens" ON user_device_tokens
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own device tokens" ON user_device_tokens;
CREATE POLICY "Users can update their own device tokens" ON user_device_tokens
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own device tokens" ON user_device_tokens;
CREATE POLICY "Users can delete their own device tokens" ON user_device_tokens
    FOR DELETE USING (auth.uid() = user_id);

-- Enable RLS on user_device_tokens
ALTER TABLE user_device_tokens ENABLE ROW LEVEL SECURITY;
```

## 5. API Endpoints

The following endpoints are now available:

### Register Device Token
```http
POST /api/v1/notifications/register-token
Content-Type: application/json
Authorization: Bearer <access_token>

{
    "token": "fcm_device_token_here",
    "device_type": "ios|android|web",
    "device_name": "iPhone 15 Pro"
}
```

### Unregister Device Token
```http
POST /api/v1/notifications/unregister-token
Content-Type: application/json
Authorization: Bearer <access_token>

{
    "token": "fcm_device_token_here",
    "device_type": "ios|android|web"
}
```

### Test Notification
```http
GET /api/v1/notifications/test
Authorization: Bearer <access_token>
```

## 6. Frontend Integration

### React Native Setup

1. Install Firebase SDK:
```bash
npm install @react-native-firebase/app @react-native-firebase/messaging
```

2. Configure Firebase:
```javascript
// firebase.config.js
import { initializeApp } from '@react-native-firebase/app';

const firebaseConfig = {
  projectId: 'your-firebase-project-id',
  // Add other config as needed
};

export default initializeApp(firebaseConfig);
```

3. Request permissions and get token:
```javascript
import messaging from '@react-native-firebase/messaging';

// Request permission
const requestPermission = async () => {
  const authStatus = await messaging().requestPermission();
  const enabled = authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
                  authStatus === messaging.AuthorizationStatus.PROVISIONAL;
  
  if (enabled) {
    const token = await messaging().getToken();
    // Register token with your backend
    await registerDeviceToken(token);
  }
};

// Register device token
const registerDeviceToken = async (token) => {
  await fetch('/api/v1/notifications/register-token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({
      token,
      device_type: 'ios', // or 'android'
      device_name: 'iPhone 15 Pro'
    })
  });
};
```

### Web Setup

1. Install Firebase SDK:
```bash
npm install firebase
```

2. Initialize Firebase:
```javascript
import { initializeApp } from 'firebase/app';
import { getMessaging, getToken } from 'firebase/messaging';

const firebaseConfig = {
  projectId: 'your-firebase-project-id',
  // Add other config
};

const app = initializeApp(firebaseConfig);
const messaging = getMessaging(app);

// Get token
const getFCMToken = async () => {
  try {
    const token = await getToken(messaging, {
      vapidKey: 'your-vapid-key' // Get from Firebase Console
    });
    return token;
  } catch (error) {
    console.error('Error getting FCM token:', error);
  }
};
```

## 7. Notification Types

The system sends notifications for:

### Message Notifications
- **Event Messages**: Notifies all event participants except sender
- **Direct Messages**: Notifies the recipient
- **Data**: `{type: "message", sender_name: "John Doe", event_id: "optional"}`

### Video Call Notifications
- **Event Video Calls**: Notifies all event participants except caller
- **Direct Video Calls**: Notifies the recipient
- **Data**: `{type: "video_call", caller_name: "John Doe", event_id: "optional"}`

## 8. Testing

1. Start your backend server
2. Register a device token using the API
3. Send a test notification:
```bash
curl -X GET "http://localhost:8000/api/v1/notifications/test" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 9. Troubleshooting

### Common Issues

1. **"FCM v1 API not configured"**: Check your environment variables
2. **"No device tokens found"**: Ensure device is registered
3. **"Failed to send notification"**: Check Firebase project configuration

### Debug Logs

The FCM service logs all operations. Check your server logs for:
- ✅ Successful notifications
- ❌ Failed notifications
- 🔍 Configuration issues

### Firebase Console

Monitor notifications in Firebase Console:
1. Go to "Engage" → "Messaging"
2. View delivery reports and analytics

## 10. Security Notes

- Keep your service account key secure
- Never commit credentials to version control
- Use environment variables for all sensitive data
- Regularly rotate service account keys
- Monitor FCM usage and costs

## 11. Production Considerations

- Set up proper error handling and retry logic
- Monitor notification delivery rates
- Implement notification preferences
- Consider rate limiting for high-volume apps
- Set up monitoring and alerting for FCM failures
