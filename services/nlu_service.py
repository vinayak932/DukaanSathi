
from services.intent_parser import detect_intent
from services.llm_service import understand_message


def understand_user_message(text):
    """
    Hybrid NLU:
    1. Try rule-based intent detection.
    2. Use Groq when the rule result is unknown or
       does not have high confidence.
    """

    if not text or not text.strip():
        return {
            "intent": "unknown",
            "confidence": "low",
            "entities": {},
            "needs_clarification": True,
            "clarification_reason": "Empty message",
            "response": "Kripya dobara boliye."
        }

    rule_result = detect_intent(text)

    # Fast path for clearly recognised greetings.
    if (
        rule_result["intent"] == "greeting"
        and rule_result["confidence"] == "high"
    ):
        return {
            "intent": "greeting",
            "confidence": "high",
            "entities": {},
            "needs_clarification": False,
            "clarification_reason": None,
            "response": "Namaste! Main Chotu hoon. Bataiye, kya kaam hai?"
        }

    # Use Groq for natural-language understanding.
    llm_result = understand_message(text)

    return llm_result
