import os
import json
import logging
import re
import time
import threading
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

# In-memory conversation cache with TTL
# { session_id: {"messages": [{role, content}], "timestamp": epoch_seconds} }
conversations = {}
CACHE_TTL_SECONDS = 1800
MAX_CACHE_SIZE = 1000
_CACHE_LOCK = threading.Lock()


def _prune_cache():
    with _CACHE_LOCK:
        now = time.time()
        expired = [sid for sid, data in conversations.items()
                   if now - data.get("timestamp", 0) > CACHE_TTL_SECONDS]
        for sid in expired:
            del conversations[sid]
        if len(conversations) > MAX_CACHE_SIZE:
            sorted_by_age = sorted(conversations.items(), key=lambda x: x[1].get("timestamp", 0))
            for sid, _ in sorted_by_age[:100]:
                del conversations[sid]


def get_session_history(session_id: str) -> list:
    with _CACHE_LOCK:
        _prune_cache()
        data = conversations.get(session_id)
        if data is None:
            return []
        return data["messages"][-10:]


def save_to_history(session_id: str, role: str, content: str):
    with _CACHE_LOCK:
        now = time.time()
        if session_id not in conversations:
            conversations[session_id] = {"messages": [], "timestamp": now}
        conversations[session_id]["messages"].append({"role": role, "content": content})
        conversations[session_id]["timestamp"] = now
        if len(conversations[session_id]["messages"]) > 20:
            conversations[session_id]["messages"] = conversations[session_id]["messages"][-20:]
        _prune_cache()


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'###?\s*', '', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text.strip()


MAX_MSG_LENGTH = 4096


def _chunk_text(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LENGTH:
        return [text]
    return [text[i:i + MAX_MSG_LENGTH] for i in range(0, len(text), MAX_MSG_LENGTH)]

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "backend_url": BACKEND_URL}), 200

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

        if response.status_code == 503:
            ai_response = "🙏 The Guru is deep in meditation. Please try again in a moment."
        elif response.status_code == 429:
            ai_response = "🙏 Please wait a moment before your next question."
        elif response.status_code == 500:
            ai_response = "🙏 The Guru needs a moment. Please try again shortly."
        else:
            response.raise_for_status()
            data = response.json()
            ai_response = data.get("response", "I apologize, something went wrong.")

        ai_response = strip_markdown(ai_response)

        save_to_history(session_id, "user", incoming_msg)
        # Only save assistant response if backend call was successful (2xx)
        if 200 <= response.status_code < 300:
            save_to_history(session_id, "assistant", ai_response)

        resp = MessagingResponse()
        for chunk in _chunk_text(ai_response):
            resp.message(chunk)
        return str(resp)

    except requests.exceptions.Timeout:
        logger.error("Timeout connecting to AskMukthiGuru backend.")
        resp = MessagingResponse()
        resp.message("🙏 The Guru is taking longer than usual. Please try again.")
        return str(resp)
    except requests.exceptions.ConnectionError:
        logger.error("Connection error connecting to AskMukthiGuru backend.")
        resp = MessagingResponse()
        resp.message("🙏 Unable to reach the Guru. Please check your connection.")
        return str(resp)
    except Exception as e:
        logger.error(f"Error handling Twilio webhook: {e}", exc_info=True)
        resp = MessagingResponse()
        resp.message("🙏 Something went unexpectedly quiet on my end. Could you try again?")
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

        if response.status_code == 503:
            ai_response = "🙏 The Guru is deep in meditation. Please try again in a moment."
        elif response.status_code == 429:
            ai_response = "🙏 Please wait a moment before your next question."
        elif response.status_code == 500:
            ai_response = "🙏 The Guru needs a moment. Please try again shortly."
        else:
            response.raise_for_status()
            data = response.json()
            ai_response = data.get("response", "I apologize, something went wrong.")

        ai_response = strip_markdown(ai_response)

        save_to_history(session_id, "user", msg_body)
        # Only save assistant response if backend call was successful (2xx)
        if 200 <= response.status_code < 300:
            save_to_history(session_id, "assistant", ai_response)

        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if not whatsapp_token:
            logger.error("Missing WHATSAPP_TOKEN environment variable. Cannot reply to Meta.")
            return 'Missing WHATSAPP_TOKEN', 500

        for chunk in _chunk_text(ai_response):
            meta_response = requests.post(
                f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "to": from_number,
                    "text": {"body": chunk}
                },
                headers={
                    "Authorization": f"Bearer {whatsapp_token}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            meta_response.raise_for_status()
        return 'OK', 200

    except requests.exceptions.Timeout:
        logger.error("Timeout connecting to AskMukthiGuru backend for Meta webhook.")
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            try:
                requests.post(
                    f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "text": {"body": "🙏 The Guru is taking longer than usual. Please try again."}
                    },
                    headers={"Authorization": f"Bearer {whatsapp_token}", "Content-Type": "application/json"},
                    timeout=10
                )
            except Exception:
                pass
        return '🙏 The Guru is taking longer than usual. Please try again.', 200
    except requests.exceptions.ConnectionError:
        logger.error("Connection error connecting to AskMukthiGuru backend for Meta webhook.")
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            try:
                requests.post(
                    f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "text": {"body": "🙏 Unable to reach the Guru. Please check your connection."}
                    },
                    headers={"Authorization": f"Bearer {whatsapp_token}", "Content-Type": "application/json"},
                    timeout=10
                )
            except Exception:
                pass
        return '🙏 Unable to reach the Guru. Please check your connection.', 200
    except Exception as e:
        logger.error(f"Error handling Meta webhook: {e}", exc_info=True)
        whatsapp_token = os.getenv('WHATSAPP_TOKEN')
        if whatsapp_token and 'from_number' in locals() and 'phone_number_id' in locals():
            try:
                requests.post(
                    f"https://graph.facebook.com/v18.0/{phone_number_id}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "text": {"body": "🙏 Something went unexpectedly quiet on my end. Could you try again?"}
                    },
                    headers={"Authorization": f"Bearer {whatsapp_token}", "Content-Type": "application/json"},
                    timeout=10
                )
            except Exception:
                pass
        return '🙏 Something went unexpectedly quiet on my end. Could you try again?', 200

if __name__ == '__main__':
    logger.info(f"Starting WhatsApp Webhook broker on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT)
