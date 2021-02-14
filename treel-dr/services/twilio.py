from twilio.rest import Client
from logging import Logger, getLogger
from config import TWILIO_AUTH_TOKEN, TWILIO_NUMBER, TWILIO_SID

class TwilioService:
    def __init__(self, logger: Logger = None):
        if not logger:
            logger = getLogger("TwilioServiceLogger")
        self._logger = logger
        self._client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

    def send_text(self, phone_number: str, text: str):
        message = self._client.messages.create(
                        body=text,
                        from_=TWILIO_NUMBER,
                        to=phone_number
                    )
        print(message)
        return True