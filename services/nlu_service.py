
import logging

from services.intent_parser import detect_intent
from services.llm_service import understand_message


logger = logging.getLogger(__name__)


def build_safe_response(
    response="Maaf kijiye, main samajh nahi paaya. Kripya dobara boliye."
):
    return {
        "intent": "unknown",
        "confidence": "low",
        "entities": {
            "customer": None,
            "items": [],
            "amount": None,
            "payment_method": None
        },
        "needs_clarification": True,
        "clarification_reason": "AI service unavailable or unable to interpret the message.",
        "response": response
    }


def understand_user_message(text, context=None):

    if not text or not text.strip():
        return build_safe_response("Kripya dobara boliye.")

    rule_result = detect_intent(text)

    # Greetings do not need an LLM call.
    if (
        rule_result["intent"] == "greeting"
        and rule_result["confidence"] == "high"
    ):
        return {
            "intent": "greeting",
            "confidence": "high",
            "entities": {
                "customer": None,
                "items": [],
                "amount": None,
                "payment_method": None
            },
            "needs_clarification": False,
            "clarification_reason": None,
            "response": "Namaste! Main Chotu hoon. Bataiye, kya kaam hai?"
        }

    try:
        return understand_message(text, context=context)

    except Exception:
        logger.exception("Groq NLU failed.")

        # During an existing repayment conversation, the
        # conversation manager can still use its deterministic
        # amount and payment-method extraction.
        if context:
            return {
                "intent": "record_payment",
                "confidence": "low",
                "entities": {
                    "customer": None,
                    "items": [],
                    "amount": None,
                    "payment_method": None
                },
                "needs_clarification": True,
                "clarification_reason": "Groq unavailable during repayment reply.",
                "response": "Maaf kijiye, dobara bataiye."
            }

        # Never start a new transaction based only on regex intent.
        # The rule parser does not safely extract all required entities.
        return build_safe_response(
            "Abhi AI service se connection nahi ho pa raha hai. "
            "Kripya thodi der baad dobara boliye."
        )
