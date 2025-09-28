# Simple FCM Setup Guide

## **Option 1: Server Key (Simplest)**

This is the easiest way to get started with FCM.

### 1. Get Server Key from Firebase Console
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project (or create one)
3. Go to **Project Settings** → **Cloud Messaging** tab
4. Copy the **Server Key** (starts with `AAAA...`)

### 2. Add to Environment
Add this single line to your `.env` file:

```env
FCM_SERVER_KEY=AAAA...your-server-key-here
```

### 3. That's it! 
Your FCM service will now work with just the server key.

---

## **Option 2: Full Firebase Setup (More Secure)**

If you want the more secure v1 API approach:

### 1. Create Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your Firebase project
3. Go to **IAM & Admin** → **Service Accounts**
4. Create service account with **Firebase Cloud Messaging Admin** role
5. Download the JSON key file

### 2. Add to Environment
```env
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----"
FIREBASE_CLIENT_EMAIL=your-service-account@project.iam.gserviceaccount.com
```

---

## **What You Actually Need**

### For Backend (Sending Notifications):
- ✅ **Server Key** (simplest) OR
- ✅ **Service Account** (more secure)

### For Frontend (Receiving Notifications):
- ✅ **Firebase Web Config** (for web apps)
- ✅ **Google Services files** (for mobile apps)

---

## **Quick Test**

1. Set up your server key in `.env`
2. Start your backend
3. Register a device token via API
4. Send test notification:
```bash
curl -X GET "http://localhost:8000/api/v1/notifications/test" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## **Recommendation**

**Start with Option 1 (Server Key)** - it's the simplest and works perfectly for most use cases. You can always upgrade to the full service account approach later if needed.
