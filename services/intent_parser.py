import re

def normalize_text(text):
    if not isinstance(text, str):
        return ""

    return re.sub(r"\s+", " ", text.lower().strip())


def detect_intent(text):
    text = normalize_text(text)

    if not text:
        return {
            "intent": "unknown",
            "confidence": "low",
            "message": "Please say that again."
        }

    # 1. Repayment of existing udhaar.
    # Keep these patterns before sale patterns.
    payment_received_patterns = [
        r"udhaar.*(wapas|jama|chuka|bhar)",
        r"(payment|paise|rupaye).*(mile|mili|mila|jama hue)",
        r"(udhaar|khata).*(clear|settle)",
        r"(purana udhaar|baaki paise)",
        r"(wapas|jama|chuka).*(udhaar|paise)",
        r"(received|got).*(payment|money)"
    ]

    if any(re.search(p, text) for p in payment_received_patterns):
        return {
            "intent": "record_payment",
            "confidence": "medium",
            "message": "This appears to be a customer repayment."
        }

    # 2. Queries about existing shop records.
    record_query_patterns = [
        r"(aaj|kal).*(kitni|kitna).*(sale|bikri|munafa)",
        r"(kitna|kitni).*(udhaar|baaki)",
        r"(balance|khata).*(batao|dikhao|kitna)",
        r"(sales|transactions).*(history|dikhao|batao)",
        r"(aaj|kal).*(kitna|kitni).*(kamaya|becha)",
        r"(total|kul).*(sale|bikri)",
        r"(customer|grahak).*(udhaar|balance|khata)",
        r"(stock|inventory).*(batao|dikhao|kitna)",
        r"(kitna|kitni).*(stock|inventory)",
        r"(stock|inventory).*(bacha|remaining|left|available|kam|low|khatam)",
        r"(kaun|kon).*(product|products|samaan).*(kam|bache|khatam)",
        r"(low stock|out of stock|stock khatam|stock kam)"
    ]

    if any(re.search(p, text) for p in record_query_patterns):
        return {
            "intent": "query_records",
            "confidence": "medium",
            "message": "This appears to be a records query."
        }

    # 3. Explicit calculation requests.
    calculation_patterns = [
        r"(kitne ka|kitne ki|kitna hua|kitni hui)",
        r"(total|jod|hisab|calculate)",
        r"(kitna padega|kitni padegi|price batao)",
        r"(kitna milega|kitni milegi)",
        r"(calculator|hisab lagao)",
        r"(multiply|multiplication|divide|division)",
        r"(plus|minus|into)"
    ]

    if any(re.search(p, text) for p in calculation_patterns):
        return {
            "intent": "calculate",
            "confidence": "medium",
            "message": "This appears to be a calculation request."
        }

    # 4. Explicit sale instructions.
    sale_patterns = [
        r"(bech diya|bech diye|bech do|bech dena)",
        r"(sale record karo|sale kar do|record kar do)",
        r"(de diya|de diye|de do|de dena)",
        r"(bik gaya|bik gaye)",
        r"(maal diya|samaan diya)",
        r"udhaar.*(diya|diye|de diya|de diye)",
        r"(likh do|jod do).*(khate|udhaar)"
    ]

    if any(re.search(p, text) for p in sale_patterns):
        return {
            "intent": "record_sale",
            "confidence": "medium",
            "message": "This appears to be a sale instruction."
        }

    # 5. Greetings.
    greeting_patterns = [
        r"^(hello|hi|hey)(\s|$)",
        r"^namaste(\s|$)",
        r"^namaskar(\s|$)",
        r"^hello chotu(\s|$)",
        r"^hi chotu(\s|$)"
    ]

    if any(re.search(p, text) for p in greeting_patterns):
        return {
            "intent": "greeting",
            "confidence": "high",
            "message": "Greeting detected."
        }

    return {
        "intent": "unknown",
        "confidence": "low",
        "message": "I need clarification before proceeding."
    }


def detect_sales_query_type(text):
    text = normalize_text(text)

    # Cash sales
    if any(word in text for word in [
        "नकद", "कैश", "cash"
    ]):
        return "cash"

    # UPI sales
    if any(word in text for word in [
        "upi", "यूपीआई", "ऑनलाइन पेमेंट"
    ]):
        return "upi"

    # Credit sales
    if any(word in text for word in [
        "उधार", "उधारी", "udhaar", "credit"
    ]):
        return "udhaar"

    return "total"

def detect_inventory_query_type(text):
    text = normalize_text(text)

    # Out of stock
    if any(word in text for word in [
        "out of stock",
        "stock khatam",
        "खत्म",
        "खाली"
    ]):
        return "out_of_stock"

    # Low stock
    if any(word in text for word in [
        "low stock",
        "stock kam",
        "कम बचे",
        "कम बचा",
        "कम स्टॉक",
        "kam bache",
        "kam bacha"
    ]):
        return "low_stock"

    # Specific product stock
    if any(word in text for word in [
        "stock",
        "inventory",
        "कितना बचा",
        "कितनी बची",
        "बचा है",
        "बची है"
    ]):
        return "specific_stock"

    return "unknown"
