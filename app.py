import os
import json
import random
import re
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
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")

print(f"🔐 ACCESS_TOKEN (corto): {ACCESS_TOKEN[:10]}...")

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
    "Tómate una foto con un joven."
]

# Enviar mensajes
def send_message(recipient_id, message_text):
    payload = {
        "messaging_product": "instagram",
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    headers = {"Content-Type": "application/json"}
    INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")  # Nueva variable en Render
url = f"https://graph.facebook.com/v17.0/{INSTAGRAM_ID}/messages?access_token={ACCESS_TOKEN}"

     response = requests.post(url, headers=headers, json=payload)
    print(f"📤 Enviando mensaje a {recipient_id}: {message_text}")
    print(f"🔁 Respuesta send_message: {response.status_code} - {response.text}")

# Registrar participante
def registrar_participante(nombre, iglesia, sender_id):
    reto_asignado = random.choice(retos)
    sheet.append_row([nombre, iglesia, sender_id, reto_asignado, "0"])
    send_message(sender_id, "🎉 ¡Te has registrado exitosamente!")
    send_message(sender_id, f"📸 Tu primer reto es: {reto_asignado}")

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

# Asignar nuevo reto único
def asignar_nuevo_reto(sender_id):
    registros = sheet.get_all_records()
    retos_completados = []

    for row in registros:
        if row["ID"] == sender_id:
            retos_completados.append(row["Reto actual"])

    retos_disponibles = [r for r in retos if r not in retos_completados]
    if retos_disponibles:
        return random.choice(retos_disponibles)
    else:
        return "🏆 ¡Has completado todos los retos posibles!"

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
                nuevo_reto = asignar_nuevo_reto(sender_id)
                sheet.update_cell(i, 4, nuevo_reto)
                sheet.update_cell(i, 5, str(completados))
                send_message(sender_id, f"🔥 Nuevo reto: {nuevo_reto}")
            return
    send_message(sender_id, "⚠️ No encontré tu registro. ¿Ya te registraste?")

# Manejo de mensajes de texto
def handle_message(sender_id, text):
    text = text.lower()

    nombre_match = re.search(r"(mi nombre es|soy|me llamo)\s+(.*)", text)
    if nombre_match:
        nombre = nombre_match.group(2).strip().title()
        usuarios[sender_id] = {"nombre": nombre}
        send_message(sender_id, f"Gracias {nombre}. ¿A qué iglesia perteneces?")
        return

    iglesia_match = re.search(r"(mi iglesia es|pertenezco a|voy a la iglesia)\s+(.*)", text)
    if iglesia_match:
        if sender_id in usuarios and "nombre" in usuarios[sender_id]:
            iglesia = iglesia_match.group(2).strip().title()
            usuarios[sender_id]["iglesia"] = iglesia
            registrar_participante(usuarios[sender_id]["nombre"], iglesia, sender_id)
        else:
            send_message(sender_id, "Primero dime tu nombre. Ej: 'Mi nombre es Ana'")
        return

    send_message(sender_id, "No entendí tu mensaje. Intenta con: 'Mi nombre es...' o 'Mi iglesia es...'")

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

@app.route("/")
def index():
    return "✅ Bot de Instagram activo y funcionando."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

