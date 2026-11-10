from decimal import Decimal, InvalidOperation
from services.llm_product_resolver import resolve_product_with_llm
from services.entity_extractor import find_product_match, find_customer, extract_payment_method

# Hindi and Hinglish unit names mapped to database units.
UNIT_ALIASES_HI = {
    "किलो": "kg",
    "किलोग्राम": "kg",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",

    "ग्राम": "g",
    "ग्राम्स": "g",
    "gram": "g",
    "grams": "g",
    "g": "g",

    "लीटर": "litre",
    "लिटर": "litre",
    "liter": "litre",
    "litre": "litre",

    "मिलीलीटर": "ml",
    "मिली लीटर": "ml",
    "ml": "ml",

    "पीस": "piece",
    "नग": "piece",
    "piece": "piece",

    "पैकेट": "packet",
    "पैकेट्स": "packet",
    "packet": "packet",

    "बोतल": "bottle",
    "बॉक्स": "box",
    "डिब्बा": "box",
    "दर्जन": "dozen",
    "बैग": "bag",
}


def parse_positive_decimal(value):
    """Safely convert an LLM-provided number into a positive Decimal."""
    if value is None:
        return None

    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not number.is_finite() or number <= 0:
        return None

    return number


def normalize_unit(unit):
    """Convert Hindi/Hinglish unit names into database unit names."""
    if not unit:
        return None

    cleaned = str(unit).strip().lower()
    return UNIT_ALIASES_HI.get(cleaned, cleaned)


def resolve_product_item(raw_item, products):
    """
    Resolve one extracted product against the shop's actual catalogue.
    Does not create products or modify the database.
    """
    if not isinstance(raw_item, dict):
        raw_item = {}

    product_name = raw_item.get("product")
    print("\n========== PRODUCT DEBUG ==========")
    print("Spoken product:", product_name)

    print("Available products:")
    for p in products:
        print(f"ID: {p.id} | Name: {p.name}")

    print("Local matching result:")
    debug_match = find_product_match(str(product_name), products)
    print(debug_match["status"])
    print(
        debug_match["product"].name
        if debug_match["product"] else None
    )
    print("===================================\n")

    if product_name:
        product_match = find_product_match(
            str(product_name),
            products
        )

        product_status = product_match["status"]
        product = product_match.get("product")
        product_candidates = product_match.get("candidates", [])
        product_match_type = product_match.get("match_type")

        if product_status == "NOT_FOUND":
            llm_product = resolve_product_with_llm(
                str(product_name),
                products
            )

            if llm_product:
                product = llm_product
                product_status = "FOUND"
                product_candidates = [llm_product]
                product_match_type = "llm"
    else:
        product_status = "NOT_PROVIDED"
        product = None
        product_candidates = []
        product_match_type = None

    quantity = parse_positive_decimal(raw_item.get("quantity"))
    unit = normalize_unit(raw_item.get("unit"))

    return {
        "product_name": str(product_name).strip() if product_name else None,
        "product": product,
        "product_status": product_status,
        "product_candidates": product_candidates,
        "product_match_type": product_match_type,
        "quantity": quantity,
        "unit": unit,
    }


def resolve_llm_entities(nlu_result, products, customers):
    """
    Resolve Groq-extracted entities against the current shop's database.

    products and customers MUST already be filtered by shop_id.

    Supports:
      - Multiple products through entities["items"]
      - Legacy single-product entities
      - Customer resolution
      - Quantity validation
      - Hindi/Hinglish unit normalisation
      - Payment method extraction

    This function never creates or modifies database records.
    """

    raw_entities = nlu_result.get("entities") or {}

    # 1. Resolve every product item.
    raw_items = raw_entities.get("items")

    # Backward compatibility with the previous single-product schema.
    if raw_items is None:
        if raw_entities.get("product"):
            raw_items = [{
                "product": raw_entities.get("product"),
                "quantity": raw_entities.get("quantity"),
                "unit": raw_entities.get("unit"),
            }]
        else:
            raw_items = []

    if not isinstance(raw_items, list):
        raw_items = []

    items = [
        resolve_product_item(raw_item, products)
        for raw_item in raw_items
    ]

    # 2. Determine the overall product resolution status.
    if not items:
        product_status = "NOT_PROVIDED"
    elif any(item["product_status"] == "AMBIGUOUS" for item in items):
        product_status = "AMBIGUOUS"
    elif any(item["product_status"] == "NOT_FOUND" for item in items):
        product_status = "NOT_FOUND"
    elif any(item["product_status"] == "NOT_PROVIDED" for item in items):
        product_status = "NOT_PROVIDED"
    elif all(item["product_status"] == "FOUND" for item in items):
        product_status = "FOUND"
    else:
        product_status = "NOT_PROVIDED"

    # 3. Resolve customer against this shop's customers.
    customer_name = raw_entities.get("customer")

    if customer_name:
        customer = find_customer(str(customer_name), customers)
        customer_status = "FOUND" if customer else "NOT_FOUND"
    else:
        customer = None
        customer_status = "NOT_PROVIDED"

    # 4. Validate amount.
    amount = parse_positive_decimal(raw_entities.get("amount"))

    # 5. Normalize payment method.
    raw_payment = raw_entities.get("payment_method")
    payment_method = (
        extract_payment_method(str(raw_payment))
        if raw_payment else None
    )

    # 6. Preserve legacy single-product fields.
    first_item = items[0] if items else {}

    return {
        # New multi-product structure
        "items": items,

        # Overall product status
        "product_status": product_status,

        # Legacy fields: first item
        "product": first_item.get("product"),
        "product_candidates": first_item.get("product_candidates", []),
        "product_match_type": first_item.get("product_match_type"),
        "quantity": first_item.get("quantity"),
        "unit": first_item.get("unit"),

        # Customer
        "customer": customer,
        "customer_status": customer_status,
        # Preserve the spoken name when it is not in this shop's database.
        # start_sale_conversation() uses this to ask before creating a customer.
        "customer_name": (
            str(customer_name).strip()
            if customer_name and customer is None else None
        ),

        # Payment
        "amount": amount,
        "payment_method": payment_method,
    }
