import os
import json
import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# --------------------
# Load OpenAI
# --------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# --------------------
# Load Google Calendar Credentials
# --------------------
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
creds_info = json.loads(GOOGLE_CREDS_JSON)
credentials = service_account.Credentials.from_service_account_info(
    creds_info,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)
CALENDAR_ID = "primary"  # using your Gmail calendar for now


# --------------------
# Appointment Booking Helper
# --------------------
def create_calendar_event(name, appointment_time, appointment_type):
    """Creates a Google Calendar event."""
    event = {
        "summary": f"Appointment – {name} ({appointment_type})",
        "description": "Booked via WhatsApp AI Receptionist",
        "start": {"dateTime": appointment_time.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {
            "dateTime": (appointment_time + datetime.timedelta(minutes=15)).isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }

    calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


# --------------------
# WhatsApp Endpoint
# --------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.form.get("Body", "").lower().strip()
    sender = request.form.get("From", "")

    print("Message from:", sender)
    print("Body:", incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()

    # --------------------
    # Handle Appointment Booking
    # --------------------
    if "book" in incoming_msg or "appointment" in incoming_msg:
        msg.body("Sure 😊 — what is your **full name**?")
        return str(resp)

    # Ask name
    elif incoming_msg.startswith("name:"):
        user_name = incoming_msg.replace("name:", "").strip()
        msg.body(f"Thanks {user_name}! 🙏\nPlease enter a preferred **date & time** (example: 26 Dec 5pm)")
        return str(resp)

    # Ask date & time
    elif any(x in incoming_msg for x in ["am", "pm"]) and any(month in incoming_msg for month in ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec","mon","tue","wed","thu","fri","sat","sun"]):
        user_dt = incoming_msg.replace("at", "").replace("pm", " pm").replace("am", " am")
        try:
            dt = datetime.datetime.strptime(user_dt, "%d %b %I %p")
            # Assume this year
            dt = dt.replace(year=datetime.datetime.now().year)

            # Create calendar booking
            create_calendar_event("Patient", dt, "OPD")

            msg.body("🎉 Appointment confirmed!\n\n📍 *Clinic:* Chhajed Lung Care & Sleep Center\n🕒 *Time:* " + dt.strftime("%d %b %I:%M %p") + "\n\nA reminder will be sent ✔️")
            return str(resp)
        except:
            msg.body("❌ Could not understand the date — please type like:\n\n26 Dec 5pm")
            return str(resp)

    # --------------------
    # FAQs
    # --------------------
    if "timing" in incoming_msg or "open" in incoming_msg:
        msg.body("🕒 Clinic Hours:\nMon, Tue, Thu, Sat – 1:30pm to 6:30pm")
        return str(resp)

    if "location" in incoming_msg or "where" in incoming_msg or "address" in incoming_msg:
        msg.body("📍 Address:\nA-405, Sangam Junction of S V Road & Saibaba Road,\nSantacruz (West), Mumbai 400054")
        return str(resp)

    if "doctor" in incoming_msg or "who" in incoming_msg:
        msg.body("👨‍⚕️ Doctor: *Dr. Prashant Chhajed* (Lung Specialist & Sleep Medicine)")
        return str(resp)

    # --------------------
    # Default fallback to AI
    # --------------------
    ai_answer = client.responses.create(
        model="gpt-5-mini",
        input=f"You are an AI receptionist for a lung clinic. Reply to: {incoming_msg}"
    )
    msg.body(ai_answer.output_text)
    return str(resp)


# --------------------
# Run Flask
# --------------------
if __name__ == "__main__":
    app.run(port=10000, debug=True)
