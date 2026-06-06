import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration (loaded from environment or defaults)
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
BACKEND_TOKEN = os.getenv('BACKEND_TOKEN', '')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', 'MukthiGuruVerifyToken123')
PORT = int(os.getenv('PORT', 5000))

# Simple in-memory conversation cache (use Redis in production)
# Structure: { session_id: [ {role: "user", content: "..."}, ... ] }
conversations = {}

def get_session_history(session_id: str) -> list:
    """Retrieve the last 10 messages of conversation history."""
    history = conversations.get(session_id, [])
    return history[-10:]

def save_to_history(session_id: str, role: str, content: str):
    """Save a message to history."""
    if session_id not in conversations:
        conversations[session_id] = []
    conversations[session_id].append({"role": role, "content": content})
    # Cap to prevent unbounded growth
    if len(conversations[session_id]) > 20:
        conversations[session_id] = conversations[session_id][-20:]

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "webhook": "whatsapp"}), 200

# ── 1. TWILIO WEBHOOK ROUTE ──
@app.route('/whatsapp/twilio', methods=['POST'])
def twilio_webhook():
    """Webhook handler for Twilio WhatsApp incoming messages."""
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').replace('whatsapp:', '').strip()
    
    if not incoming_msg:
        logger.warning("Received empty message body from Twilio.")
        return '', 200
        
    session_id = f"whatsapp_{from_number}"
    logger.info(f"Incoming Twilio message from {from_number}: {incoming_msg}")
    
    # Retrieve last 10 messages for conversation context
    history = get_session_history(session_id)
    
    try:
        # Forward message to AskMukthiGuru chat backend
        response = requests.post(
            f"{BACKEND_URL}/api/chat",
            json={
                "messages": history,
                "user_message": incoming_msg,
                "session_id": session_id,
                "language": "en"
            },
            headers={
                "Authorization": f"Bearer {BACKEND_TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        response.raise_for_status()
        data = response.json()
        ai_response = data.get("response", "I apologize, something went wrong.")
        
        # Save both user and AI messages in local history
        save_to_history(session_id, "user", incoming_msg)
        save_to_history(session_id, "assistant", ai_response)
        
        # Respond back using Twilio TwiML
        resp = MessagingResponse()
        resp.message(ai_response)
        return str(resp)
        
    except requests.exceptions.Timeout:
        logger.error("Timeout connecting to AskMukthiGuru backend.")
        resp = MessagingResponse()
        resp.message("I apologize for the delay. Please try again in a moment.")
        return str(resp)
    except Exception as e:
        logger.error(f"Error handling Twilio webhook: {e}", exc_info=True)
        resp = MessagingResponse()
        resp.message("I apologize, I'm having trouble connecting. Please try again later.")
        return str(resp)


# ── 2. META CLOUD API WEBHOOK ROUTES ──
@app.route('/whatsapp/meta', methods=['GET'])
def verify_meta_webhook():
    """Required verification route for Meta Developer webhook registration."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("Meta webhook verification successful.")
        return challenge, 200
    else:
        logger.warning("Meta webhook verification failed: Invalid verify token.")
        return 'Forbidden', 403

@app.route('/whatsapp/meta', methods=['POST'])
def meta_webhook():
    """Webhook handler for Meta Cloud API incoming messages."""
    body = request.get_json()
    logger.info(f"Incoming Meta payload: {json.dumps(body)}")
    
    # Extract message details
    try:
        entry = body.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        message = value.get('messages', [{}])[0]
        
        if not message:
            return 'No message payload', 200
            
        from_number = message.get('from')
        msg_body = message.get('text', {}).get('body', '').strip()
        phone_number_id = value.get('metadata', {}).get('phone_number_id')
        
        if not msg_body or not from_number or not phone_number_id:
            return 'Incomplete payload', 200
            
    except (IndexError, KeyError, AttributeError):
        return 'Ignored non-message event', 200
        
    session_id = f"whatsapp_{from_number}"
    history = get_session_history(session_id)
    
    try:
        # Forward to AskMukthiGuru chat backend
        response = requests.post(
            f"{BACKEND_URL}/api/chat",
            json={
                "messages": history,
                "user_message": msg_body,
                "session_id": session_id,
                "language": "en"
            },
            headers={
                "Authorization": f"Bearer {BACKEND_TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        ai_response = data.get("response", "I apologize, something went wrong.")
        
        save_to_history(session_id, "user", msg_body)
        save_to_history(session_id, "assistant", ai_response)
        
        # Send response back using Meta Cloud messaging endpoint
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if not whatsapp_token:
            logger.error("Missing WHATSAPP_TOKEN environment variable. Cannot reply to Meta.")
            return 'Missing WHATSAPP_TOKEN', 500
            
        meta_response = requests.post(
            f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": from_number,
                "text": {"body": ai_response}
            },
            headers={
                "Authorization": f"Bearer {whatsapp_token}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        meta_response.raise_for_status()
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Error handling Meta webhook: {e}", exc_info=True)
        return 'Internal Server Error', 500

if __name__ == '__main__':
    logger.info(f"Starting WhatsApp Webhook broker on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT)
