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

ACCESS_TOKEN = os.getenv("EAAItRKRWhG4BO1QZAhnRz7ecNnNsJhniLZAb6iMlPy2M1MQ0QwFTzEVOrtmo39fOlGZAaLUmoSf7N3UJZCDPa3m95ni9O2xGJASH9uY99M53bnElELB890QWlY0QOyewBvENqb91ZCDLTxIanuN5ePHUjLS8OXbyukJIBhLWWjZAIMwgZCANwzZBaUGE")
PAGE_ID = os.getenv("608583202336837")
VERIFY_TOKEN = os.getenv("mi_token_secreto")

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

usuarios = {}

retos = [
    "Tómate una foto con un anciano.",
    "Tómate una foto con un niño pequeño.",
    "Tómate una foto con un vendedor ambulante.",
    "Tómate una foto con una persona con una mascota.",
    "Tómate una foto con una pareja.",
    "Tómate una foto con un adulto.",
    "Tómate una foto con un joven.",
]

def send_message(recipient_id, message_text):
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    headers = {"Content-Type": "application/json"}
    url = f"https://graph.facebook.com/v17.0/{PAGE_ID}/messages?access_token={ACCESS_TOKEN}"
    response = requests.post(url, headers=headers, json=payload)
    print("✅ Respuesta de send_message:", response.status_code, response.text)

def registrar_participante(nombre, iglesia, sender_id):
    reto_asignado = random.choice(retos)
    sheet.append_row([nombre, iglesia, sender_id, reto_asignado, "0"])
    send_message(sender_id, "🎉 ¡Te has registrado exitosamente!")
    send_message(sender_id, f"📸 Tu primer reto es: {reto_asignado}")

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
        send_message(sender_id, "


