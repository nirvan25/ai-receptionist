import os
import json
import datetime
import dateparser
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# Load OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load Google Calendar credentials
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
creds_info = json.loads(GOOGLE_CREDS_JSON)
credentials = service_account.Credentials.from_service_account_info(
    creds_info,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)
CALENDAR_ID = "primary"
TIMEZONE = "Asia/Kolkata"

# ---- SESSION MEMORY ----
sessions = {}  # phone_number: {fields, step}

CLINIC_DAYS = ["monday", "tuesday", "thursday", "saturday"]
CLINIC_OPEN = datetime.time(13, 30)  # 1:30 PM
CLINIC_CLOSE = datetime.time(18, 30) # 6:30 PM


def is_clinic_open(dt: datetime.datetime) -> bool:
    weekday = dt.strftime("%A").lower()
    if weekday not in CLINIC_DAYS:
        return False
    if not (CLINIC_OPEN <= dt.time() <= CLINIC_CLOSE):
        return False
    return True


def create_calendar_event(name, dt, reason, phone, consult_type):
    event = {
        "summary": f"Appointment – {name} ({consult_type})",
        "description": f"Reason: {reason}\nPhone: {phone}",
        "start": {"dateTime": dt.isoformat(), "timeZone": TIMEZONE},
        "end": {
            "dateTime": (dt + datetime.timedelta(minutes=15)).isoformat(),
            "timeZone": TIMEZONE,
        },
    }
    calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


def extract_info(message: str):
    """Ask GPT to extract info from free text."""
    response = client.responses.create(
        model="gpt-5-mini",
        input=f"""
Extract structured appointment info from this text:
"{message}"

Return ONLY JSON with keys:
name, phone, reason, type (OPD or VIDEO), datetime (convert to natural language if possible)
""")
    return response.output_text


def update_session(phone, user_msg, session):
    """Update session fields using GPT extraction."""
    try:
        data = json.loads(extract_info(user_msg))
    except:
        data = {}

    for field in ["name", "phone", "reason", "type", "datetime"]:
        if field in data and data[field] and not session.get(field):
            session[field] = data[field]

    # Parse datetime
    if session.get("datetime") and not isinstance(session.get("datetime"), datetime.datetime):
        parsed = dateparser.parse(session["datetime"], settings={"TIMEZONE": TIMEZONE})
        if parsed:
            session["datetime"] = parsed

    return session


def missing_fields(session):
    """Return list of still-missing required fields."""
    required = ["name", "datetime", "reason"]
    return [f for f in required if not session.get(f)]


def summarize(session):
    dt = session["datetime"]
    return (
        f"📅 {dt.strftime('%d %b %I:%M %p')}\n"
        f"👤 {session['name']}\n"
        f"☎️ {session.get('phone','-')}\n"
        f"📌 Reason: {session['reason']}\n"
        f"🏥 Type: {session.get('type','OPD')}"
    )


# ---- MAIN WHATSAPP LOGIC ----
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    msg = request.form.get("Body", "").strip()
    phone = request.form.get("From", "").replace("whatsapp:", "")

    res = MessagingResponse()
    reply = res.message()

    # start new session if needed
    if phone not in sessions:
        sessions[phone] = {"step": "start"}

    s = sessions[phone]

    # greeting
    if msg.lower() in ["hi", "hello", "hey", "namaste"]:
        reply.body("Hello 👋 How can I help you?\n(appointment • timings • location)")
        return Response(str(res), mimetype="application/xml")

    # user asks for appointment
    if "book" in msg.lower() or "appointment" in msg.lower():
        s["step"] = "collect"
        reply.body("Sure 😊 Tell me what's your name?")
        return Response(str(res), mimetype="application/xml")

    # update extracted info
    s = update_session(phone, msg, s)
    sessions[phone] = s

    # Ask missing fields one-by-one
    missing = missing_fields(s)
    if missing:
        next_field = missing[0]
        prompts = {
            "name": "Your name?",
            "datetime": "Which day & time?",
            "reason": "Reason for visit?"
        }
        reply.body(prompts[next_field])
        return Response(str(res), mimetype="application/xml")

    # Validate clinic hours
    dt = s["datetime"]
    if not is_clinic_open(dt):
        reply.body("⛔ Clinic is only open Mon/Tue/Thu/Sat, 1:30–6:30pm.\nPick another time 🙂")
        s["datetime"] = None
        return Response(str(res), mimetype="application/xml")

    # Ask confirmation before booking
    if s.get("step") != "confirm":
        s["step"] = "confirm"
        reply.body("Almost done 👇\n\n" + summarize(s) + "\n\nReply YES to confirm or NO to change.")
        return Response(str(res), mimetype="application/xml")

    # Handle confirmation
    if msg.lower() == "yes":
        create_calendar_event(
            s["name"],
            s["datetime"],
            s["reason"],
            s.get("phone", ""),
            s.get("type", "OPD")
        )
        sessions.pop(phone, None)
        reply.body("✔️ Booked. Thank you — see you soon!")
        return Response(str(res), mimetype="application/xml")

    if msg.lower() == "no":
        sessions[phone] = {"step": "collect"}  # restart data
        reply.body("Okay — tell me new date & time 😊")
        return Response(str(res), mimetype="application/xml")

    reply.body("Please reply YES or NO")
    return Response(str(res), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
