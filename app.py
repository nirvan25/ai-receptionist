from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os

app = Flask(__name__)

print("🔥 PHASE-4 — APPOINTMENT BOOKING ENABLED — LOADED 🔥")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---- Temporary in-memory session store ----
sessions = {}  # { phone: { "name":None, "date":None, "slot":None, "type":None } }


# ---- Clinic Info ----
CLINIC_INFO = """
Clinic Name: Chhajed Lung Care & Sleep Center
Doctor: Dr. Prashant Chhajed (Pulmonologist)
Location: A-405, Sangam Junction of S V Road and Saibaba Road, Santacruz (West), Mumbai – 400054
Timings: Monday, Tuesday, Thursday, Saturday from 1:30 PM – 6:30 PM
Consultation Types: OPD consultation or Video consultation
"""

SYSTEM_PROMPT = f"""
You are an AI receptionist for Chhajed Lung Care & Sleep Center.
NEVER give medical advice.
If medical questions appear, ALWAYS say:
"Only Dr. Chhajed can provide medical advice. I can help you book an appointment — would you like OPD or Video consultation?"
Keep responses short (2-4 lines).

Clinic info:
{CLINIC_INFO}
"""


# ---- GPT Wrapper ----
def gpt_reply(msg):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()


# ---- Helper for starting a new session ----
def start_session(phone):
    sessions[phone] = {"name": None, "date": None, "slot": None, "type": None}


# ---- Appointment Flow Logic ----
def handle_appointment(phone, msg):
    # Create session if not exists
    if phone not in sessions:
        start_session(phone)
        return "Sure 👍, let's book your appointment. First, may I know your *full name*?"

    session = sessions[phone]

    if session["name"] is None:
        session["name"] = msg
        return "Thank you. Which *date* would you prefer? (e.g. 25 Jan)"

    if session["date"] is None:
        session["date"] = msg
        return "Great. What *time slot* suits you?\n• Afternoon (1:30-3:30)\n• Evening (4:00-6:30)"

    if session["slot"] is None:
        session["slot"] = msg
        return "Noted 👍\nWould you like *OPD* or *Video Consultation*?"

    if session["type"] is None:
        session["type"] = msg

        # Final summary
        summary = (
            f"🗓 *Appointment Request Summary*\n"
            f"👤 Name: {session['name']}\n"
            f"📅 Date: {session['date']}\n"
            f"⏰ Time: {session['slot']}\n"
            f"🏥 Type: {session['type']}\n"
            f"☎️ Phone: {phone.replace('whatsapp:', '')}\n\n"
            f"Please reply *YES* to confirm or *NO* to cancel."
        )
        return summary

    # Confirmation handling
    if msg.lower() == "yes":
        del sessions[phone]
        return "✔️ Thank you. Your appointment request is submitted.\nOur team will contact you shortly to confirm exact timing."

    if msg.lower() == "no":
        del sessions[phone]
        return "❌ Appointment cancelled. Let me know if you want to book again."

    return "Please reply *YES* or *NO*."


# ---- WhatsApp Route ----
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    msg = request.form.get("Body", "").strip()
    phone = request.form.get("From", "")

    print(f"📩 Message from {phone}: {msg}")

    # Greeting handler
    if msg.lower() in ["hi", "hello", "hey", "namaste"]:
        return twilio_response(
            "Hello 👋 Welcome to *Chhajed Lung Care & Sleep Center*.\n"
            "I’m your AI assistant.\n"
            "How can I help you today?\n"
            "• Timings\n• Location\n• OPD / Video Appointment"
        )

    # Detect appointment intent
    if "book" in msg.lower() or "appointment" in msg.lower():
        return twilio_response(handle_appointment(phone, msg))

    # Default → send GPT answer
    reply = gpt_reply(msg)
    return twilio_response(reply)


# ---- Twilio helper ----
def twilio_response(text):
    tw = MessagingResponse()
    tw.message(text)
    return Response(str(tw), mimetype="application/xml")


# ---- Local Debug ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
