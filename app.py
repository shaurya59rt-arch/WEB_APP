import os
import json
import logging
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
VERIFY_DB = "verified_devices.json"

# Environment variables for configuration
# For same-host deployment, use relative URL, otherwise use full URL
BOT_BACKEND_URL = os.getenv("BOT_BACKEND_URL", "/").strip()
if not BOT_BACKEND_URL.startswith('http'):
    # If it's a relative path, keep it relative
    BOT_BACKEND_URL = BOT_BACKEND_URL
else:
    # If it's a full URL, use it as is
    BOT_BACKEND_URL = BOT_BACKEND_URL
VERIFICATION_TIMEOUT = int(os.getenv("VERIFICATION_TIMEOUT", "10"))

def load_v_db():
    """Load local verification database"""
    if not os.path.exists(VERIFY_DB):
        return {}
    try:
        with open(VERIFY_DB, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading verification DB: {e}")
        return {}

def save_v_db(data):
    """Save local verification database"""
    try:
        with open(VERIFY_DB, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving verification DB: {e}")

@app.route('/')
def index():
    """Serve the verification page"""
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "verification-frontend",
        "bot_backend": BOT_BACKEND_URL,
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/api/config', methods=['GET'])
def get_config():
    """Return configuration for frontend"""
    return jsonify({
        "bot_backend_url": BOT_BACKEND_URL,
        "verification_timeout": VERIFICATION_TIMEOUT
    }), 200

@app.route('/api/verify', methods=['POST'])
def verify():
    """
    Main verification endpoint
    Forward verification to bot backend if it's configured as separate
    Otherwise, use local verification
    """
    try:
        data = request.json
        uip = data.get('ip')
        udevice = data.get('device')
        telegram_user_id = data.get('telegram_user_id')

        logger.info(f"Verification request from user {telegram_user_id} - ip: {uip}")

        # Validate input
        if not uip or not udevice:
            logger.warning("Missing ip or device in verification request")
            return jsonify({
                "status": "fail",
                "message": "Missing required fields: ip, device"
            }), 400

        if not telegram_user_id:
            logger.warning("Missing telegram_user_id in verification request")
            return jsonify({
                "status": "fail",
                "message": "Missing telegram_user_id"
            }), 400

        # Try to forward to bot backend
        if BOT_BACKEND_URL == "/":
            # Same-host relative URL
            bot_verify_endpoint = "/api/verify"
        else:
            bot_verify_endpoint = f"{BOT_BACKEND_URL}/api/verify"
        logger.info(f"Forwarding verification to bot backend: {bot_verify_endpoint}")

        try:
            # Convert relative URL to absolute URL if necessary
            if bot_verify_endpoint.startswith('/'):
                # Relative URL - construct full URL using current request
                base_url = request.host_url.rstrip('/')
                bot_verify_endpoint = base_url + bot_verify_endpoint
            
            response = requests.post(
                bot_verify_endpoint,
                json={
                    "ip": uip,
                    "device": udevice,
                    "telegram_user_id": int(telegram_user_id)
                },
                timeout=VERIFICATION_TIMEOUT
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Bot backend response: {result}")
                return jsonify(result), 200
            else:
                logger.error(f"Bot backend error: {response.status_code}")
                return jsonify({
                    "status": "fail",
                    "message": f"Verification service error: {response.status_code}"
                }), response.status_code

        except requests.exceptions.ConnectionError:
            logger.warning(f"Cannot connect to bot backend: {bot_verify_endpoint}")
            # Fallback to local verification if bot backend is unreachable
            return local_verify(uip, udevice, telegram_user_id)

        except requests.exceptions.Timeout:
            logger.error(f"Bot backend timeout: {bot_verify_endpoint}")
            return jsonify({
                "status": "fail",
                "message": "Verification service timeout. Please try again."
            }), 504

        except Exception as e:
            logger.error(f"Error connecting to bot backend: {e}")
            return jsonify({
                "status": "fail",
                "message": f"Error: {str(e)[:100]}"
            }), 500

    except Exception as e:
        logger.error(f"Verification endpoint error: {e}", exc_info=True)
        return jsonify({
            "status": "fail",
            "message": f"Server error: {str(e)[:100]}"
        }), 500

def local_verify(uip, udevice, telegram_user_id):
    """
    Fallback local verification (if bot backend is unreachable)
    This is only for development/testing
    """
    logger.info(f"Using local verification for user {telegram_user_id}")
    db = load_v_db()

    # Check if (ip, device) already exists
    device_already_verified = False
    for entry in db.values():
        if entry.get('ip') == uip and entry.get('device') == udevice:
            device_already_verified = True
            logger.info(f"Device already verified locally for user {telegram_user_id}")
            break

    # Save new device
    if not device_already_verified:
        entry_id = str(len(db) + 1)
        db[entry_id] = {
            "ip": uip,
            "device": udevice,
            "telegram_user_id": int(telegram_user_id),
            "timestamp": datetime.now().isoformat()
        }
        save_v_db(db)
        logger.info(f"New device saved locally")

    # Return response
    if device_already_verified:
        return jsonify({
            "status": "success",
            "message": "Same Device Detected! You can still refer and earn!",
            "device_status": "already_verified"
        }), 200
    else:
        return jsonify({
            "status": "success",
            "message": "Device Verified Successfully!",
            "device_status": "newly_verified"
        }), 200

if __name__ == '__main__':
    logger.info(f"Starting verification service")
    logger.info(f"Bot backend URL: {BOT_BACKEND_URL}")
    app.run(host='0.0.0.0', port=3000, debug=False)
