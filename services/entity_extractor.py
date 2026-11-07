
import re
from decimal import Decimal, InvalidOperation


UNIT_ALIASES = {
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "gram": "g",
    "grams": "g",
    "g": "g",
    "litre": "litre",
    "liter": "litre",
    "litres": "litre",
    "liters": "litre",
    "ml": "ml",
    "millilitre": "ml",
    "piece": "piece",
    "pieces": "piece",
    "packet": "packet",
    "packets": "packet",
    "bottle": "bottle",
    "bottles": "bottle",
    "box": "box",
    "boxes": "box",
    "dozen": "dozen",
    "bag": "bag",
    "bags": "bag"
}


PAYMENT_ALIASES = {
    "cash": "cash",
    "nagad": "cash",
    "upi": "upi",
    "online": "upi",
    "phonepe": "upi",
    "google pay": "upi",
    "gpay": "upi",
    "paytm": "upi",
    "udhaar": "udhaar",
    "credit": "udhaar"
}


def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_amount(text):
    patterns = [
        r"₹\s*(\d+(?:\.\d+)?)",
        r"\b(\d+(?:\.\d+)?)\s*(?:rupees|rupee|rupaye|rupya|rs\.?)\b",
        r"\b(\d+(?:\.\d+)?)\s*(?:rupaye|rupya)\s*(?:ki|ka|ke)?"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            try:
                return Decimal(match.group(1))
            except InvalidOperation:
                return None

    return None


def extract_quantity(text):
    pattern = (
        r"\b(\d+(?:\.\d+)?)\s*"
        r"(kg|kilo|kilos|kilogram|kilograms|g|gram|grams|"
        r"litre|liter|litres|liters|ml|"
        r"piece|pieces|packet|packets|bottle|bottles|"
        r"box|boxes|dozen|bag|bags)\b"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None, None

    quantity = Decimal(match.group(1))
    spoken_unit = match.group(2).lower()

    return quantity, UNIT_ALIASES.get(spoken_unit)


def find_product(text, products):
    """
    Match a product name from this shop's inventory.

    Longest matching name wins to reduce ambiguity.
    """

    normalized_text = normalize(text)

    matches = []

    for product in products:
        product_name = normalize(product.name)

        if re.search(
            rf"(?<!\w){re.escape(product_name)}(?!\w)",
            normalized_text
        ):
            matches.append(product)

    if not matches:
        return None

    matches.sort(
        key=lambda product: len(product.name),
        reverse=True
    )

    if (
        len(matches) > 1
        and len(matches[0].name) == len(matches[1].name)
    ):
        return None

    return matches[0]


def find_customer(text, customers):
    normalized_text = normalize(text)

    matches = []

    for customer in customers:
        customer_name = normalize(customer.name)

        if re.search(
            rf"(?<!\w){re.escape(customer_name)}(?!\w)",
            normalized_text
        ):
            matches.append(customer)

    if not matches:
        return None

    matches.sort(
        key=lambda customer: len(customer.name),
        reverse=True
    )

    if (
        len(matches) > 1
        and len(matches[0].name) == len(matches[1].name)
    ):
        return None

    return matches[0]


def extract_payment_method(text):
    normalized_text = normalize(text)

    for phrase, method in PAYMENT_ALIASES.items():
        if re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            normalized_text
        ):
            return method

    return None


def extract_entities(text, products, customers):
    normalized_text = normalize(text)

    product = find_product(normalized_text, products)
    customer = find_customer(normalized_text, customers)

    quantity, unit = extract_quantity(normalized_text)
    amount = extract_amount(normalized_text)

    payment_method = extract_payment_method(normalized_text)

    return {
        "product": product,
        "customer": customer,
        "quantity": quantity,
        "unit": unit,
        "amount": amount,
        "payment_method": payment_method
    }
