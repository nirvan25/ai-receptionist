from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os

app = Flask(__name__)

# Debug marker – must appear in Render logs
print("🔥 PHASE-3 AI RECEPTIONIST — POLISHED & SAFE — LOADED 🔥")

# Initialize OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Clinic information
CLINIC_INFO = """
Clinic Name: Chhajed Lung Care & Sleep Center
Doctor: Dr. Prashant Chhajed (Pulmonologist)
Location: A-405, Sangam Junction of S V Road and Saibaba Road, Santacruz (West), Mumbai – 400054
Timings: Monday, Tuesday, Thursday, Saturday from 1:30 PM – 6:30 PM
Consultation Types: OPD consultation or Video consultation
Appointment Duration: 15 minutes
"""

# SYSTEM RULES – controls tone, restrictions & purpose
SYSTEM_PROMPT = f"""
You are an AI receptionist for Chhajed Lung Care & Sleep Center.
Your job:
- Answer clinic-related questions concisely (2–4 short lines).
- Help patients schedule appointments by asking remaining info step-by-step.
- Redirect ANY medical-symptom questions to Dr. Chhajed and offer appointment.

STRICT RULES:
- NEVER provide medical advice, medicine names, diagnosis, or treatment suggestions.
- If a medical question appears, ALWAYS say:
  "Only Dr. Chhajed can provide medical advice. I can help you book an appointment — would you like OPD or Video consultation?"
- Use warm, polite, supportive tone.
- Include emojis sparingly (1–2), friendly but not childish.
- Write messages in plain Indian English.

Clinic info:
{CLINIC_INFO}
"""

# Generate AI reply through OpenAI
def get_ai_reply(user_message: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    user_message = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")

    print(f"📩 Incoming WhatsApp message from {from_number}: {user_message}")

    # ✨ Smart greeting logic
    if user_message.lower() in ["hi", "hello", "hey", "namaste"]:
        reply_text = (
            "Hello 👋 Welcome to *Chhajed Lung Care & Sleep Center*.\n"
            "I’m your AI assistant.\n"
            "How can I help you today?\n"
            "• Timings\n• Location\n• OPD / Video Appointment"
        )
    else:
        try:
            reply_text = get_ai_reply(user_message)
        except Exception as e:
            print("❌ OpenAI Error:", str(e))
            reply_text = (
                "I'm having trouble replying right now 😅\n"
                "But I can still help you with:\n"
                "• Clinic timings\n• Location\n• OPD / Video appointments\n"
                "Please type your question again."
            )

    # Send WhatsApp XML response
    twilio_resp = MessagingResponse()
    twilio_resp.message(reply_text)
    return Response(str(twilio_resp), mimetype="application/xml")

# Main — LOCAL DEV ONLY
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
