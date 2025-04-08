import os
import json
import random
import requests
import gspread
from flask import Flask, request
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.cloud import vision

# Cargar variables de entorno
load_dotenv()

# Configuración y tokens
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_secreto")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "TU_ACCESS_TOKEN_AQUI")
PAGE_ID = os.getenv("PAGE_ID")

# ID de prueba para enviar mensaje al arrancar
TEST_RECIPIENT_ID = "642412358760680"

# Inicializar Flask
app = Flask(__name__)

# Cargar credenciales de Google
cred_string = os.getenv("CREDENTIALS_JSON")
if not cred_string:
    raise Exception("❌ Variable de entorno CREDENTIALS_JSON no encontrada.")

try:
    credenciales_dict = json.loads(cred_string)
except json.JSONDecodeError:
    raise Exception("❌ Error al parsear CREDENTIALS_JSON.")

with open("credenciales.json", "w") as f:
    json.dump(credenciales_dict, f)

try:
    creds = Credentials.from_service_account_info(
        credenciales_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    vision_client = vision.ImageAnnotatorClient.from_service_account_info(credenciales_dict)
except Exception as e:
    raise Exception(f"❌ Error al cargar las credenciales: {str(e)}")

# Conexión con Google Sheets
client = gspread.authorize(creds)
sheet = client.open_by_key("1_ZSk0z7Lp81rT-bBz4fmSJj0eyGjVWvrUZm432QzgoM").sheet1

# Almacenamiento temporal
usuarios = {}

# Retos disponibles
retos = [
    "Tómate una foto con un anciano.",
    "Tómate una foto con un niño pequeño.",
    "Tómate una foto con un vendedor ambulante.",
    "Tómate una foto con una persona con una mascota.",
    "Tómate una foto con una pareja.",
    "Tómate una foto con un adulto.",
    "Tómate una foto con un joven.",
]

# Enviar mensajes por la API de Meta con logs
def send_message(recipient_id, message_text):
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"https://graph.facebook.com/v17.0/me/messages?access_token={ACCESS_TOKEN}",
        headers=headers,
        json=payload
    )
    print(f"📤 Enviando mensaje a {recipient_id}: {message_text}")
    print(f"🔁 Respuesta send_message: {response.status_code} - {response.text}")

# Enviar mensaje de prueba al iniciar
@app.before_first_request
def mensaje_de_prueba():
    print("🚀 Enviando mensaje de prueba inicial...")
    send_message(TEST_RECIPIENT_ID, "✅ Este es un mensaje de prueba enviado automáticamente.")

# Registrar participante
def registrar_participante(nombre, iglesia, sender_id):
    reto_asignado = random.choice(retos)
    sheet.append_row([nombre, iglesia, sender_id, reto_asignado, "0"])
    send_message(sender_id, "🎉 ¡Te has registrado exitosamente!")
    send_message(sender_id, f"📸 Tu primer reto es: {reto_asignado}")

# Manejo de mensajes de texto
def handle_message(sender_id, text):
    if "mi nombre es" in text.lower():
        nombre = text.split("mi nombre es")[-1].strip()
        usuarios[sender_id] = {"nombre": nombre}
        send_message(sender_id, "Gracias. ¿A qué iglesia perteneces?")
    elif "mi iglesia es" in text.lower():
        if sender_id in usuarios and "nombre" in usuarios[sender_id]:
            iglesia = text.split("mi iglesia es")[-1].strip()
            usuarios[sender_id]["iglesia"] = iglesia
            registrar_participante(usuarios[sender_id]["nombre"], iglesia, sender_id)
        else:
            send_message(sender_id, "Primero dime tu nombre.")
    else:
        send_message(sender_id, "No entendí tu mensaje. Intenta con: 'Mi nombre es...'")

# Analizar imagen con Vision
def analizar_imagen(sender_id, image_url):
    response = requests.get(image_url)
    if response.status_code != 200:
        send_message(sender_id, "❌ Hubo un problema al descargar tu imagen.")
        return

    image = vision.Image(content=response.content)
    vision_response = vision_client.face_detection(image=image)
    faces = vision_response.face_annotations

    if len(faces) >= 1:
        send_message(sender_id, f"✅ ¡Foto recibida! Detecté {len(faces)} persona(s). ¡Buen trabajo!")
        marcar_reto_completado(sender_id)
    else:
        send_message(sender_id, "❌ No detecté personas en la imagen. Intenta con otra foto.")

# Marcar reto como completado en Sheets
def marcar_reto_completado(sender_id):
    registros = sheet.get_all_records()
    for i, row in enumerate(registros, start=2):
        if row["ID"] == sender_id:
            completados = int(row["Retos completados"]) + 1
            if completados >= 7:
                sheet.update_cell(i, 5, str(completados))
                send_message(sender_id, "🎉 ¡Has completado 7 retos! Ahora pasarás a la siguiente fase. 🎯")
            else:
                nuevo_reto = random.choice(retos)
                sheet.update_cell(i, 4, nuevo_reto)
                sheet.update_cell(i, 5, str(completados))
                send_message(sender_id, f"🔥 Nuevo reto: {nuevo_reto}")
            return
    send_message(sender_id, "⚠️ No encontré tu registro. ¿Ya te registraste?")

# Webhook principal
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Token inválido", 403

    elif request.method == "POST":
        data = request.get_json()
        print("📩 Mensaje recibido:", json.dumps(data, indent=2))

        if data.get("entry"):
            for entry in data["entry"]:
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event["sender"]["id"]
                    message = messaging_event.get("message", {})
                    if "text" in message:
                        handle_message(sender_id, message["text"])
                    elif "attachments" in message:
                        for att in message["attachments"]:
                            if att["type"] == "image":
                                analizar_imagen(sender_id, att["payload"]["url"])

                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if change.get("field") == "messages":
                        messages = value.get("messages", [])
                        for msg in messages:
                            sender_id = msg.get("from")
                            text = msg.get("text", {}).get("body")
                            image = msg.get("image", {})
                            if sender_id and text:
                                handle_message(sender_id, text)
                            elif sender_id and image:
                                analizar_imagen(sender_id, image.get("url"))
        return "EVENT_RECEIVED", 200

# Página de prueba
@app.before_first_request
def iniciar_bot():
    print("🚀 Enviando mensaje de prueba inicial...")
    send_message(TEST_RECIPIENT_ID, "✅ Este es un mensaje de prueba enviado automáticamente.")


# Ejecutar app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


