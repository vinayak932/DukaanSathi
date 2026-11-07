import re

def normalize_text(text):
    return re.sub(r"\s+", " ", text.lower().strip())


def detect_intent(text):
    text = normalize_text(text)

    if not text:
        return {
            "intent": "unknown",
            "confidence": "low",
            "message": "Please say that again."
        }

    # 1. Payment received against existing udhaar
    payment_received_patterns = [
        r"\budhaar\b.*\b(wapas|jama|chuka|bhar)\b",
        r"\b(payment|paise|rupaye)\b.*\b(mile|mili|mila|jama hue)\b",
        r"\b(udhaar|khata)\b.*\b(clear|settle)\b",
        r"\b(purana udhaar|baaki paise)\b"
    ]

    if any(re.search(p, text) for p in payment_received_patterns):
        return {
            "intent": "record_payment",
            "confidence": "medium",
            "message": "This appears to be a customer payment."
        }

    # 2. Queries about existing records
    record_query_patterns = [
        r"\b(aaj|kal)\b.*\b(kitni|kitna)\b.*\b(sale|bikri|munafa)\b",
        r"\b(kitna|kitni)\b.*\b(udhaar|baaki)\b",
        r"\b(balance|khata)\b.*\b(batao|dikhao|kitna)\b",
        r"\b(sales|transactions)\b.*\b(history|dikhao|batao)\b"
    ]

    if any(re.search(p, text) for p in record_query_patterns):
        return {
            "intent": "query_records",
            "confidence": "medium",
            "message": "This appears to be a records query."
        }

    # 3. Explicit calculation questions
    calculation_patterns = [
        r"\b(kitne ka|kitne ki|kitna hua|kitni hui)\b",
        r"\b(total|jod|jama|hisab|calculate)\b",
        r"\b(kitna padega|kitni padegi|price batao)\b",
        r"\b(kitna milega|kitni milegi)\b",
        r"\b(calculator|hisab lagao)\b"
    ]

    if any(re.search(p, text) for p in calculation_patterns):
        return {
            "intent": "calculate",
            "confidence": "high",
            "message": "This is a calculation request."
        }

    # 4. Explicit sale instructions
    sale_patterns = [
        r"\b(bech diya|bech diye|bech do|bech dena)\b",
        r"\b(sale record karo|sale kar do|record kar do)\b",
        r"\b(de diya|de diye|de do|de dena)\b",
        r"\b(bik gaya|bik gaye)\b",
        r"\b(maal diya|samaan diya)\b",
        r"\budhaar\b.*\b(diya|diye|de diya|de diye)\b",
    ]

    if any(re.search(p, text) for p in sale_patterns):
        return {
            "intent": "record_sale",
            "confidence": "medium",
            "message": "This appears to be a sale instruction."
        }

    #5. Greeting
    greeting_patterns = [
        r"^hello\b",
        r"^hi\b",
        r"^namaste\b",
        r"^namaskar\b",
        r"^hey\b",
        r"^hello chotu\b"
    ]

    if any(re.search(p, text) for p in greeting_patterns):
        return {
            "intent": "greeting",
            "confidence": "high",
            "message": "Greeting detected."
        }

    # 5. Ambiguous or unsupported requests
    return {
        "intent": "unknown",
        "confidence": "low",
        "message": "I need clarification before proceeding."
    }
