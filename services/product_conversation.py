import re
from decimal import Decimal, InvalidOperation
from services.slot_extractor import extract_conversation_slots

UNIT_ALIASES = {
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "किलो": "kg",
    "किलोग्राम": "kg",

    "g": "g",
    "gram": "g",
    "grams": "g",
    "ग्राम": "g",

    "litre": "litre",
    "liter": "litre",
    "लीटर": "litre",
    "लिटर": "litre",

    "ml": "ml",
    "मिलीलीटर": "ml",

    "piece": "piece",
    "pieces": "piece",
    "पीस": "piece",
    "नग": "piece",

    "packet": "packet",
    "packets": "packet",
    "पैकेट": "packet",

    "box": "box",
    "बॉक्स": "box",
    "डिब्बा": "box",

    "bottle": "bottle",
    "बोतल": "bottle",

    "dozen": "dozen",
    "दर्जन": "dozen",

    "bag": "bag",
    "बैग": "bag",
}


def parse_number(text):
    """Extract one positive or non-negative decimal number."""
    if text is None:
        return None

    match = re.search(r"(?<!\w)\d+(?:\.\d+)?(?!\w)", str(text))

    if not match:
        return None

    try:
        number = Decimal(match.group())
    except InvalidOperation:
        return None

    if not number.is_finite():
        return None

    return number


def parse_price(text, allow_zero=False):
    """Extract a valid price from a reply."""
    number = parse_number(text)

    if number is None:
        return None

    if number < 0 or (number == 0 and not allow_zero):
        return None

    return number.quantize(Decimal("0.01"))


def parse_unit(text):
    """Resolve a unit mentioned in the reply."""
    cleaned = str(text).strip().lower()

    # Match longer unit names first.
    for alias in sorted(UNIT_ALIASES, key=len, reverse=True):
        if re.search(
            r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
            cleaned
        ):
            return UNIT_ALIASES[alias]

    return None


def parse_stock(text):
    """Extract a non-negative opening stock quantity."""
    number = parse_number(text)

    if number is None or number < 0:
        return None

    return number.quantize(Decimal("0.001"))


def start_product_conversation(
    product_name,
    unit=None,
    original_sale=None
):
    """
    Start product registration.

    original_sale preserves the transaction that triggered
    the missing-product workflow.
    """

    if not product_name or not str(product_name).strip():
        raise ValueError("Product name is required.")

    normalized_unit = parse_unit(unit) if unit else None

    pending = {
        "action": "add_product",
        "workflow": "product_creation",
        "awaiting": None,

        "new_product": {
            "name": str(product_name).strip(),
            "unit": normalized_unit,
            "cost_price": None,
            "selling_price": None,
            "stock_quantity": None,
        },

        "original_sale": original_sale,
    }

    if not normalized_unit:
        pending["awaiting"] = "unit"
        response = (
            f"{product_name} kis unit mein rakhte hain? "
            "Jaise kg, litre, packet ya piece."
        )
    else:
        pending["awaiting"] = "cost_price"
        response = (
            f"Aapne {product_name} kitne rupaye mein "
            f"ek {normalized_unit} kharida?"
        )

    return pending, response


def process_product_reply(reply, pending):
    """
    Extract all details from the latest reply, update the pending
    product, and ask only for information that is still missing.
    """

    if not pending or pending.get("workflow") != "product_creation":
        return {
            "status": "NO_PENDING",
            "pending": None,
            "response": "Abhi product registration pending nahi hai."
        }

    answer = str(reply).strip()

    if not answer:
        return {
            "status": "CONTINUE",
            "pending": pending,
            "response": "Kripya dobara bataiye."
        }

    cancel_words = {
        "cancel", "cancel karo", "rehne do",
        "nahi", "radd karo", "radd kar do"
    }

    if answer.lower() in cancel_words:
        return {
            "status": "CANCELLED",
            "pending": None,
            "response": "Theek hai, product add karna cancel kar diya."
        }

    product = pending["new_product"]

    # Extract every field mentioned in the latest reply.
    updates = extract_conversation_slots(
        workflow="product_creation",
        reply=answer,
        current_state={
            "new_product": product,
            "awaiting": pending.get("awaiting")
        }
    )

    # Update only fields explicitly extracted.
    if "unit" in updates:
        unit = parse_unit(updates["unit"])

        if unit is None:
            return {
                "status": "CONTINUE",
                "pending": pending,
                "response": (
                    "Unit samajh nahi aayi. "
                    "Kg, litre, packet ya piece mein bataiye."
                )
            }

        product["unit"] = unit

    if "cost_price" in updates:
        product["cost_price"] = updates["cost_price"]

    if "selling_price" in updates:
        selling_price = Decimal(updates["selling_price"])

        if selling_price <= 0:
            return {
                "status": "CONTINUE",
                "pending": pending,
                "response": "Bechne ka daam zero se zyada hona chahiye."
            }

        product["selling_price"] = updates["selling_price"]

    if "stock_quantity" in updates:
        product["stock_quantity"] = updates["stock_quantity"]

    # Determine the next missing field.
    if not product.get("unit"):
        pending["awaiting"] = "unit"
        response = (
            f"{product['name']} kis unit mein rakhte hain? "
            "Jaise kg, litre, packet ya piece."
        )

    elif product.get("cost_price") is None:
        pending["awaiting"] = "cost_price"
        response = (
            f"Aapne {product['name']} kitne rupaye mein "
            f"ek {product['unit']} kharida?"
        )

    elif product.get("selling_price") is None:
        pending["awaiting"] = "selling_price"
        response = (
            f"Aur ek {product['unit']} kitne rupaye mein bechoge?"
        )

    elif product.get("stock_quantity") is None:
        pending["awaiting"] = "stock_quantity"
        response = (
            f"Abhi kitna {product['name']} stock mein rakha hai? "
            f"{product['unit']} mein bataiye."
        )

    else:
        pending["awaiting"] = "ready_to_create"

        return {
            "status": "READY_TO_CREATE",
            "pending": pending,
            "response": (
                f"{product['name']}: kharidne ka daam "
                f"₹{product['cost_price']} per {product['unit']}, "
                f"bechne ka daam ₹{product['selling_price']} per "
                f"{product['unit']}, aur stock "
                f"{product['stock_quantity']} {product['unit']}. "
                "Saari details mil gayi hain."
            )
        }

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }
