import os
import json
import datetime
import dateparser
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from openai import OpenAI

app = Flask(__name__)

# ---- Load keys ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

RECEPTIONIST_NUMBER = "+917738889949"  # Clinic receptionist

TIMEZONE = "Asia/Kolkata"

# ---- Session memory ----
SESSIONS = {}  # phone -> {name, datetime, reason, user_phone, step}

CLINIC_DAYS = ["monday", "tuesday", "thursday", "saturday"]
CLINIC_OPEN = datetime.time(13, 30)
CLINIC_CLOSE = datetime.time(18, 30)


def is_clinic_open(dt):
    weekday = dt.strftime("%A").lower()
    if weekday not in CLINIC_DAYS:
        return False
    if not (CLINIC_OPEN <= dt.time() <= CLINIC_CLOSE):
        return False
    return True


def extract_info(text):
    """Extract appointment info using GPT."""
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""
Extract structured appointment info ONLY as JSON:
Fields:
name, datetime (natural language OK), reason, phone

Input:
{text}
"""
    )
    try:
        return json.loads(response.output_text)
    except:
        return {}


def update_session(phone, msg, session):
    data = extract_info(msg)

    for key in ["name", "datetime", "reason", "phone"]:
        if key in data and data[key] and not session.get(key):
            session[key] = data[key]

    # Parse datetime → datetime object
    if session.get("datetime") and not isinstance(session["datetime"], datetime.datetime):
        parsed = dateparser.parse(session["datetime"], settings={"TIMEZONE": TIMEZONE})
        if parsed:
            session["datetime"] = parsed

    return session


def missing_fields(s):
    required = ["name", "datetime", "reason", "phone"]
    return [f for f in required if not s.get(f)]


def forward_to_receptionist(s):
    text = (
        "📩 *New Appointment — Lung Clinic*\n\n"
        f"👤 *Name:* {s['name']}\n"
        f"📞 *Patient WhatsApp:* +91{s['phone']}\n"
        f"📅 *Appointment:* {s['datetime'].strftime('%d %b – %I:%M %p')}\n"
        f"📝 *Reason:* {s['reason']}\n"
    )
    twilio_client.messages.create(
        from_="whatsapp:+14155238886",  # Twilio sandbox sender
        to=f"whatsapp:{RECEPTIONIST_NUMBER}",
        body=text
    )


@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    msg = request.form.get("Body", "").strip()
    phone = request.form.get("From", "").replace("whatsapp:", "")

    res = MessagingResponse()
    reply = res.message()

    # start new session
    if phone not in SESSIONS:
        SESSIONS[phone] = {"step": "start"}

    s = SESSIONS[phone]

    # greeting
    if msg.lower() in ["hi", "hello", "hey"]:
        reply.body("Hello 👋 How can I help?\n(appointment • timings • location)")
        return Response(str(res), mimetype="application/xml")

    # if user mentions appointment
    if "book" in msg.lower() or "appointment" in msg.lower():
        s["step"] = "collect"
        reply.body("Sure 😊 What's your name?")
        return Response(str(res), mimetype="application/xml")

    # update extracted info using GPT
    s = update_session(phone, msg, s)
    SESSIONS[phone] = s

    # ask missing info in short
    missing = missing_fields(s)
    if missing:
        prompts = {
            "name": "Your full name?",
            "datetime": "Preferred day & time?",
            "reason": "Reason to visit?",
            "phone": "WhatsApp number I should share with clinic? (digits only)"
        }
        reply.body(prompts[missing[0]])
        return Response(str(res), mimetype="application/xml")

    # validate time
    dt = s["datetime"]
    if not is_clinic_open(dt):
        reply.body("⛔ Clinic open only Mon/Tue/Thu/Sat — 1:30–6:30pm. Pick another time 🙂")
        s["datetime"] = None
        return Response(str(res), mimetype="application/xml")

    # FINAL – send info to receptionist
    forward_to_receptionist(s)
    reply.body("📩 Thank you — your details are noted.\nOur team will call you shortly to confirm.")
    SESSIONS.pop(phone, None)
    return Response(str(res), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
