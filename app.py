from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """
    This function is called by Twilio whenever
    a WhatsApp message is received.
    """

    # Log incoming message (useful for debugging)
    incoming_msg = request.form.get("Body", "")
    from_number = request.form.get("From", "")
    print(f"Message from {from_number}: {incoming_msg}")

    # Create Twilio response
    response = MessagingResponse()
    response.message(
        "Hello! 👋 This is the AI receptionist. How can I help you today?"
    )

    # Return valid TwiML XML
    return Response(str(response), mimetype="application/xml")


# Required for Render deployment
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
