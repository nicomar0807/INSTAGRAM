import os
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")


@app.route('/', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("Webhook verificado correctamente")
        return challenge, 200
    else:
        print("Fallo en la verificación del webhook")
        return "Error de verificación", 403


@app.route('/', methods=['POST'])
def handle_messages():
    data = request.get_json()
    print(json.dumps(data, indent=2))  # Para ver los datos que llegan desde Meta

    if 'entry' in data:
        for entry in data['entry']:
            if 'messaging' in entry.get('changes', [{}])[0]:
                message_event = entry['changes'][0]['messaging'][0]
                sender_id = message_event['sender']['id']
                message_text = message_event.get('message', {}).get('text', '')

                # Responder al usuario
                if message_text:
                    send_message(sender_id, f"¡Hola! Gracias por tu mensaje. ¿Cuál es tu nombre e iglesia?")
    
    return "EVENT_RECEIVED", 200


def send_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ID}/messages"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE",
        "access_token": PAGE_ACCESS_TOKEN
    }

    response = requests.post(url, headers=headers, json=payload)
    print(f"Respuesta de Meta: {response.status_code} - {response.text}")
    return response.json()


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5000)), debug=True)


