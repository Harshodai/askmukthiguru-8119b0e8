# WhatsApp Bot Integration Guide

This guide explains how to integrate a WhatsApp bot with the AskMukthiGuru backend `/api/chat` endpoint.

## Overview

The AskMukthiGuru backend provides a REST API endpoint at `/api/chat` that accepts chat messages and returns AI-generated spiritual guidance responses. You can connect any WhatsApp bot service to this endpoint to provide the spiritual guidance experience over WhatsApp.

## Prerequisites

1. **WhatsApp Business Account** - Set up through one of:
   - [Twilio WhatsApp API](https://www.twilio.com/whatsapp)
   - [WhatsApp Business API](https://business.whatsapp.com/)
   - [Meta Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
   
2. **Backend Access** - Your AskMukthiGuru backend URL and authentication credentials

3. **Webhook Server** - A server to receive WhatsApp messages and forward them to the backend

## Architecture

```
WhatsApp User
    ↓
WhatsApp Platform (Twilio/Meta)
    ↓
Your Webhook Server
    ↓
AskMukthiGuru Backend (/api/chat)
    ↓
AI Response
    ↓
Back to WhatsApp User
```

## API Endpoint Reference

### POST /api/chat

**Endpoint:** `https://your-backend-domain.com/api/chat`

**Authentication:** Required (Bearer token)

**Headers:**
```http
Content-Type: application/json
Authorization: Bearer <your-jwt-token>
```

**Request Body:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Previous user message"
    },
    {
      "role": "assistant",
      "content": "Previous assistant response"
    }
  ],
  "user_message": "What is the path to inner peace?",
  "session_id": "whatsapp_<phone_number>",
  "meditation_step": 0,
  "language": "en"
}
```

**Response:**
```json
{
  "response": "Inner peace begins with awareness of your thoughts...",
  "intent": "QUERY",
  "meditation_step": 0,
  "citations": [
    "https://youtube.com/watch?v=example"
  ],
  "blocked": false,
  "trace_id": "abc123",
  "latency_ms": 1234
}
```

## Implementation Examples

### 1. Twilio WhatsApp Integration

#### Step 1: Set up Twilio Webhook

```python
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
import os

app = Flask(__name__)

BACKEND_URL = os.getenv('BACKEND_URL', 'https://your-backend.com')
BACKEND_TOKEN = os.getenv('BACKEND_TOKEN')

# Store conversation history (use Redis/Database in production)
conversations = {}

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages"""
    # Get message details
    incoming_msg = request.values.get('Body', '')
    from_number = request.values.get('From', '')
    
    # Get or create conversation history
    session_id = f"whatsapp_{from_number.replace('whatsapp:', '')}"
    if session_id not in conversations:
        conversations[session_id] = []
    
    # Call AskMukthiGuru backend
    try:
        response = requests.post(
            f'{BACKEND_URL}/api/chat',
            json={
                'messages': conversations[session_id][-10:],  # Last 10 messages
                'user_message': incoming_msg,
                'session_id': session_id,
                'language': 'en'
            },
            headers={
                'Authorization': f'Bearer {BACKEND_TOKEN}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Update conversation history
        conversations[session_id].append({
            'role': 'user',
            'content': incoming_msg
        })
        conversations[session_id].append({
            'role': 'assistant',
            'content': data['response']
        })
        
        # Send response back to WhatsApp
        resp = MessagingResponse()
        resp.message(data['response'])
        
        return str(resp)
        
    except Exception as e:
        resp = MessagingResponse()
        resp.message("I apologize, I'm having trouble connecting. Please try again in a moment.")
        return str(resp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

#### Step 2: Configure Twilio

1. Go to Twilio Console > WhatsApp Senders
2. Set webhook URL to: `https://your-webhook-server.com/whatsapp`
3. Enable incoming messages

### 2. Meta Cloud API Integration

```javascript
// Node.js Express example
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());

const BACKEND_URL = process.env.BACKEND_URL;
const BACKEND_TOKEN = process.env.BACKEND_TOKEN;
const WHATSAPP_TOKEN = process.env.WHATSAPP_TOKEN;
const PHONE_NUMBER_ID = process.env.PHONE_NUMBER_ID;

// Store conversations (use Redis/Database in production)
const conversations = new Map();

// Webhook verification (required by Meta)
app.get('/webhook', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];
  
  if (mode === 'subscribe' && token === process.env.VERIFY_TOKEN) {
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});

// Receive messages
app.post('/webhook', async (req, res) => {
  try {
    const entry = req.body.entry?.[0];
    const change = entry?.changes?.[0];
    const message = change?.value?.messages?.[0];
    
    if (!message) {
      return res.sendStatus(200);
    }
    
    const from = message.from;
    const msgBody = message.text?.body;
    
    if (!msgBody) {
      return res.sendStatus(200);
    }
    
    // Get conversation history
    const sessionId = `whatsapp_${from}`;
    const history = conversations.get(sessionId) || [];
    
    // Call AskMukthiGuru backend
    const response = await axios.post(
      `${BACKEND_URL}/api/chat`,
      {
        messages: history.slice(-10),
        user_message: msgBody,
        session_id: sessionId,
        language: 'en'
      },
      {
        headers: {
          'Authorization': `Bearer ${BACKEND_TOKEN}`,
          'Content-Type': 'application/json'
        },
        timeout: 30000
      }
    );
    
    const aiResponse = response.data.response;
    
    // Update conversation history
    history.push(
      { role: 'user', content: msgBody },
      { role: 'assistant', content: aiResponse }
    );
    conversations.set(sessionId, history);
    
    // Send response back via WhatsApp
    await axios.post(
      `https://graph.facebook.com/v18.0/${PHONE_NUMBER_ID}/messages`,
      {
        messaging_product: 'whatsapp',
        to: from,
        text: { body: aiResponse }
      },
      {
        headers: {
          'Authorization': `Bearer ${WHATSAPP_TOKEN}`,
          'Content-Type': 'application/json'
        }
      }
    );
    
    res.sendStatus(200);
    
  } catch (error) {
    console.error('Error:', error);
    res.sendStatus(500);
  }
});

app.listen(3000, () => {
  console.log('WhatsApp webhook listening on port 3000');
});
```

## Authentication

### Getting a Backend Token

The `/api/chat` endpoint requires authentication. You have two options:

#### Option 1: Service Account Token

Create a service account in your Supabase project and use the JWT token:

```bash
# Get JWT token from Supabase
BACKEND_TOKEN="your-service-role-jwt-token"
```

#### Option 2: Test Key (Development Only)

For testing, you can use the test key header:

```http
X-Test-Key: <your-jwt-secret>
```

**⚠️ Warning:** Never use test keys in production!

## Session Management

Each WhatsApp user should have a unique session ID:

```python
session_id = f"whatsapp_{phone_number}"
```

This allows the backend to:
- Maintain conversation context
- Track user preferences
- Provide personalized responses

## Conversation History

- **Store last 10 messages** for context
- **Format**: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- **Persistence**: Use Redis, MongoDB, or PostgreSQL for production

Example storage schema:

```python
{
  "session_id": "whatsapp_+1234567890",
  "messages": [
    {"role": "user", "content": "What is meditation?", "timestamp": "2025-01-15T10:00:00Z"},
    {"role": "assistant", "content": "Meditation is...", "timestamp": "2025-01-15T10:00:02Z"}
  ],
  "updated_at": "2025-01-15T10:00:02Z"
}
```

## Language Support

The backend supports multiple languages. Set the `language` parameter:

```json
{
  "language": "en"  // English
  "language": "hi"  // Hindi
  "language": "te"  // Telugu
  // ... other languages
}
```

Auto-detect language:

```python
from langdetect import detect

detected_lang = detect(incoming_message)
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid/missing token | Check Authorization header |
| `400 Bad Request` | Invalid request body | Validate JSON structure |
| `429 Too Many Requests` | Rate limit exceeded | Implement backoff strategy |
| `504 Gateway Timeout` | Backend timeout | Retry with exponential backoff |

### Error Response Example

```python
def send_whatsapp_message(to, message):
    try:
        response = requests.post(...)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        # Retry logic
        return send_fallback_message(to)
    except requests.exceptions.RequestException as e:
        logger.error(f"Backend error: {e}")
        return send_error_message(to)
```

## Rate Limiting

The backend implements rate limiting:

- **Chat endpoint**: 20 requests/minute per user
- **Global**: Varies by deployment

Implement client-side rate limiting:

```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=15, period=60)  # 15 calls per minute (buffer)
def call_backend(message):
    # Your API call here
    pass
```

## Best Practices

### 1. **Conversation Cleanup**
```python
# Clean up old conversations
def cleanup_old_conversations():
    cutoff = datetime.now() - timedelta(days=7)
    # Remove conversations older than 7 days
```

### 2. **Message Queuing**
Use a queue (Celery, RabbitMQ) for high-volume deployments:

```python
@celery.task
def process_whatsapp_message(from_number, message):
    # Process asynchronously
    pass
```

### 3. **Monitoring**
Track key metrics:
- Response time
- Error rate
- User engagement
- Token usage

```python
import statsd

client = statsd.StatsClient('localhost', 8125)

@client.timer('whatsapp.backend_latency')
def call_backend():
    # API call
    pass
```

### 4. **Graceful Degradation**
```python
def get_response(message):
    try:
        return call_backend(message)
    except Exception:
        return {
            "response": "I apologize, I'm experiencing technical difficulties. Please try again in a moment."
        }
```

## Testing

### Test the Backend Directly

```bash
curl -X POST https://your-backend.com/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "messages": [],
    "user_message": "What is inner peace?",
    "session_id": "test_session",
    "language": "en"
  }'
```

### Test WhatsApp Webhook Locally

Use ngrok for local testing:

```bash
# Start your webhook server
python app.py

# In another terminal
ngrok http 5000

# Use the ngrok URL as your webhook URL in Twilio/Meta
```

## Deployment Checklist

- [ ] Webhook server deployed and accessible
- [ ] Environment variables configured
- [ ] SSL certificate installed (required for webhooks)
- [ ] Backend authentication tested
- [ ] Conversation storage configured
- [ ] Error handling implemented
- [ ] Rate limiting configured
- [ ] Monitoring set up
- [ ] WhatsApp platform webhook configured
- [ ] Test messages sent and received

## Support & Resources

- **Backend API Docs**: `https://your-backend.com/docs`
- **Twilio WhatsApp Docs**: https://www.twilio.com/docs/whatsapp
- **Meta Cloud API Docs**: https://developers.facebook.com/docs/whatsapp/cloud-api
- **Issue Tracker**: Contact your development team

## Example: Complete Python Webhook with Redis

```python
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
import redis
import json
import os

app = Flask(__name__)

# Configuration
BACKEND_URL = os.getenv('BACKEND_URL')
BACKEND_TOKEN = os.getenv('BACKEND_TOKEN')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Redis client
redis_client = redis.from_url(REDIS_URL)

def get_conversation(session_id):
    """Get conversation history from Redis"""
    data = redis_client.get(f"conv:{session_id}")
    if data:
        return json.loads(data)
    return []

def save_conversation(session_id, messages):
    """Save conversation history to Redis"""
    redis_client.setex(
        f"conv:{session_id}",
        7 * 24 * 60 * 60,  # 7 days TTL
        json.dumps(messages)
    )

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').replace('whatsapp:', '')
    
    if not incoming_msg:
        return '', 200
    
    session_id = f"whatsapp_{from_number}"
    conversation = get_conversation(session_id)
    
    try:
        # Call backend
        response = requests.post(
            f'{BACKEND_URL}/api/chat',
            json={
                'messages': conversation[-10:],
                'user_message': incoming_msg,
                'session_id': session_id,
                'language': 'en'
            },
            headers={
                'Authorization': f'Bearer {BACKEND_TOKEN}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        response.raise_for_status()
        data = response.json()
        ai_response = data['response']
        
        # Update conversation
        conversation.append({'role': 'user', 'content': incoming_msg})
        conversation.append({'role': 'assistant', 'content': ai_response})
        save_conversation(session_id, conversation)
        
        # Send response
        resp = MessagingResponse()
        resp.message(ai_response)
        return str(resp)
        
    except requests.exceptions.Timeout:
        resp = MessagingResponse()
        resp.message("I apologize for the delay. Please try again in a moment.")
        return str(resp)
    except Exception as e:
        app.logger.error(f"Error: {e}")
        resp = MessagingResponse()
        resp.message("I apologize, something went wrong. Please try again.")
        return str(resp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
```

## Security Considerations

1. **Validate Webhook Signatures** - Verify requests are from WhatsApp
2. **Use HTTPS** - Required for production webhooks
3. **Secure Token Storage** - Use environment variables, never hardcode
4. **Rate Limiting** - Prevent abuse
5. **Input Validation** - Sanitize user messages
6. **Conversation Privacy** - Encrypt stored conversations

---

**Need Help?** Contact the development team or refer to the main project documentation at `/app/README.md`
