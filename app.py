import os
import json
import datetime
import dateparser
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from openai import OpenAI

app = Flask(__name__)

# ---- ENV KEYS ----
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
RECEPTIONIST_NUMBER = os.getenv("RECEPTIONIST_NUMBER")  # MUST exist in Render

client = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# ---- SESSION MEMORY ----
SESSIONS = {}  # phone -> {name, datetime, reason, phone, step}

TIMEZONE = "Asia/Kolkata"
CLINIC_DAYS = ["monday", "tuesday", "thursday", "saturday"]
CLINIC_OPEN = datetime.time(13, 30)   # 1:30 PM
CLINIC_CLOSE = datetime.time(18, 30)  # 6:30 PM

# ---- Helper Functions ----
def is_clinic_open(dt):
    weekday = dt.strftime("%A").lower()
    return weekday in CLINIC_DAYS and CLINIC_OPEN <= dt.time() <= CLINIC_CLOSE

def extract_info(text):
    """Extract info from user natural language using GPT"""
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""
Extract appointment info as JSON only.
Keys: name, datetime, reason, phone
Input: "{text}"
"""
    )
    try:
        return json.loads(response.output_text)
    except:
        return {}

def update_session(session, msg):
    data = extract_info(msg)
    for key in ["name", "datetime", "reason", "phone"]:
        if key in data and data[key] and not session.get(key):
            session[key] = data[key]

    # Convert datetime → datetime object
    if session.get("datetime") and not isinstance(session["datetime"], datetime.datetime):
        parsed = dateparser.parse(session["datetime"], settings={"TIMEZONE": TIMEZONE})
        if parsed:
            session["datetime"] = parsed

    return session

def missing_fields(s):
    req = ["name", "datetime", "reason", "phone"]
    return [x for x in req if not s.get(x)]

def summary_text(s):
    dt = s["datetime"]
    return (
        f"📋 *Appointment Summary*\n\n"
        f"👤 *Name:* {s['name']}\n"
        f"📞 *Patient WhatsApp:* +91{s['phone']}\n"
        f"📅 *Date:* {dt.strftime('%d %b %Y')}\n"
        f"🕒 *Time:* {dt.strftime('%I:%M %p')}\n"
        f"📝 *Reason:* {s['reason']}\n\n"
        "Reply YES to confirm or NO to change."
    )

def forward_to_receptionist(s):
    dt = s["datetime"]
    msg = (
        "📩 *New Appointment — Lung Clinic*\n\n"
        f"👤 *Name:* {s['name']}\n"
        f"📞 *Patient WhatsApp:* +91{s['phone']}\n"
        f"📅 *Appointment:* {dt.strftime('%d %b – %I:%M %p')}\n"
        f"📝 *Reason:* {s['reason']}\n"
    )
    twilio_client.messages.create(
        from_="whatsapp:+14155238886",
        to=f"whatsapp:{RECEPTIONIST_NUMBER}",
        body=msg
    )


# ---- MAIN BOT ENDPOINT ----
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    msg = request.form.get("Body", "").strip()
    phone = request.form.get("From", "").replace("whatsapp:", "")

    res = MessagingResponse()
    reply = res.message()

    if phone not in SESSIONS:
        SESSIONS[phone] = {"step": "collect"}

    s = SESSIONS[phone]

    # greetings
    if msg.lower() in ["hi", "hello", "hey"]:
        reply.body("Hello 👋 How can I help?\nType: *I want appointment*")
        return Response(str(res), mimetype="application/xml")

    if "appointment" in msg.lower():
        reply.body("Sure 😊 What's your full name?")
        return Response(str(res), mimetype="application/xml")

    # Update info using GPT
    s = update_session(s, msg)
    SESSIONS[phone] = s

    # Ask missing
    missing = missing_fields(s)
    prompts = {
        "name": "Your full name?",
        "datetime": "Preferred date & time?",
        "reason": "Reason for visit?",
        "phone": "Your WhatsApp number? (digits only)"
    }
    if missing:
        reply.body(prompts[missing[0]])
        return Response(str(res), mimetype="application/xml")

    # Validate clinic hrs
    dt = s["datetime"]
    if not is_clinic_open(dt):
        s["datetime"] = None
        reply.body("⛔ Clinic open Mon/Tue/Thu/Sat — 1:30–6:30pm.\nPick another time 🙂")
        return Response(str(res), mimetype="application/xml")

    # Confirmation step
    if s.get("step") != "confirm":
        s["step"] = "confirm"
        reply.body(summary_text(s))
        return Response(str(res), mimetype="application/xml")

    # Handle yes/no
    if msg.lower() == "yes":
        forward_to_receptionist(s)
        reply.body("📩 Details noted — our team will call you shortly to confirm 👍")
        SESSIONS.pop(phone, None)
        return Response(str(res), mimetype="application/xml")

    if msg.lower() == "no":
        SESSIONS[phone] = {"step": "collect"}
        reply.body("Okay — tell me the correct date & time 🙂")
        return Response(str(res), mimetype="application/xml")

    reply.body("Please reply YES or NO")
    return Response(str(res), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
