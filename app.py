from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os

app = Flask(__name__)

# 🔥 DEBUG MARKER — YOU MUST SEE THIS IN RENDER LOGS
print("🔥 GPT AI RECEPTIONIST VERSION LOADED 🔥")

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CLINIC_INFO = """
Clinic Name: Chhajed Lung Care & Sleep Center
Doctor: Dr. Prashant Chhajed (Pulmonologist)
Location: A-405, Sangam Junction of S V Road and Saibaba Road, Santacruz (West), Mumbai – 400054
Timings: Monday, Tuesday, Thursday, Saturday from 1:30 PM to 6:30 PM
Consultation Types: OPD consultation or Video consultation
Appointment Duration: 15 minutes
"""

SYSTEM_PROMPT = f"""
You are an AI receptionist for a medical clinic.

Your responsibilities:
- Answer clinic-related FAQs clearly and accurately.
- Help patients begin booking an appointment.
- Ask for missing details step by step (name, date, time preference, consultation type).

STRICT SAFETY RULES:
- Do NOT provide medical advice.
- Do NOT diagnose conditions.
- Do NOT recommend medicines or treatments.
- If asked a medical question, politely redirect to booking an appointment.

Clinic details:
{CLINIC_INFO}

Tone:
- Polite
- Calm
- Professional
- Human-like
"""

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

    try:
        ai_reply = get_ai_reply(user_message)
    except Exception as e:
        print("❌ OpenAI error:", str(e))
        ai_reply = (
            "Sorry, I’m facing a technical issue right now. "
            "I can still help you with clinic details or booking an appointment."
        )

    response = MessagingResponse()
    response.message(ai_reply)

    return Response(str(response), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
