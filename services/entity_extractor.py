import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher


UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "gram": "g", "grams": "g", "g": "g",
    "litre": "litre", "liter": "litre",
    "litres": "litre", "liters": "litre",
    "ml": "ml", "millilitre": "ml",
    "piece": "piece", "pieces": "piece",
    "packet": "packet", "packets": "packet",
    "bottle": "bottle", "bottles": "bottle",
    "box": "box", "boxes": "box",
    "dozen": "dozen",
    "bag": "bag", "bags": "bag"
}


PAYMENT_ALIASES = {
    "cash": "cash",
    "nagad": "cash",
    "नकद": "cash",
    "upi": "upi",
    "online": "upi",
    "phonepe": "upi",
    "google pay": "upi",
    "gpay": "upi",
    "paytm": "upi",
    "udhaar": "udhaar",
    "उधार": "udhaar",
    "credit": "udhaar"
}


# Common spoken Hindi-English product equivalents.
WORD_SYNONYMS = {
    "chawal": "rice",
    "chaawal": "rice",
    "चावल": "rice",

    "cheeni": "sugar",
    "chini": "sugar",
    "shakkar": "sugar",
    "शक्कर": "sugar",
    "चीनी": "sugar",

    "aata": "flour",
    "atta": "flour",
    "आटा": "flour",

    "tel": "oil",
    "तेल": "oil",

    "namak": "salt",
    "नमक": "salt",

    "doodh": "milk",
    "दूध": "milk"
}


FUZZY_THRESHOLD = 0.86
FUZZY_MIN_MARGIN = 0.08


def normalize(text):
    text = str(text).lower().strip()
    text = re.sub(r"[^\w\s.-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text)


def normalize_product_phrase(text):
    words = normalize(text).split()

    return " ".join(
        WORD_SYNONYMS.get(word, word)
        for word in words
    )


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


def _product_names(product):
    names = [product.name]

    names.extend(
        alias.alias
        for alias in getattr(product, "aliases", [])
        if getattr(alias, "alias", None)
    )

    return list(dict.fromkeys(
        name for name in names
        if name and str(name).strip()
    ))


def _contains_phrase(text, phrase):
    phrase = normalize_product_phrase(phrase)

    return bool(phrase) and re.search(
        rf"(?<!\w){re.escape(phrase)}(?!\w)",
        text,
        flags=re.UNICODE
    ) is not None


def _fuzzy_score(text, phrase):
    phrase = normalize_product_phrase(phrase)
    phrase_tokens = phrase.split()

    if not phrase_tokens or any(len(token) < 4 for token in phrase_tokens):
        return 0.0

    text_tokens = normalize_product_phrase(text).split()
    width = len(phrase_tokens)

    if len(text_tokens) < width:
        return 0.0

    best = 0.0

    for start in range(len(text_tokens) - width + 1):
        window = " ".join(text_tokens[start:start + width])

        best = max(
            best,
            SequenceMatcher(None, phrase, window).ratio()
        )

    return best


def _generic_product_variants(selected, products, normalized_text):
    """Find specific variants when a generic product name was spoken."""

    selected_words = normalize_product_phrase(selected.name).split()

    if len(selected_words) != 1:
        return []

    generic_word = selected_words[0]

    if not _contains_phrase(normalized_text, generic_word):
        return []

    variants = []

    for product in products:
        if product.id == selected.id:
            continue

        product_words = normalize_product_phrase(product.name).split()

        if generic_word in product_words:
            variants.append(product)

    return variants


def find_product_match(text, products):
    """
    Returns one of three statuses:

    FOUND      - Product identified.
    AMBIGUOUS  - Multiple possible products.
    NOT_FOUND  - No matching product.
    """

    normalized_text = normalize_product_phrase(text)

    candidates = []

    # First: exact product name and alias matching.
    for product in products:

        matched_lengths = [
            len(normalize_product_phrase(name))
            for name in _product_names(product)
            if _contains_phrase(normalized_text, name)
        ]

        if matched_lengths:
            candidates.append(
                (product, max(matched_lengths))
            )

    if candidates:

        best_length = max(
            length for _, length in candidates
        )

        best_products = [
            product
            for product, length in candidates
            if length == best_length
        ]

        if len(best_products) > 1:
            return {
                "status": "AMBIGUOUS",
                "product": None,
                "candidates": best_products,
                "match_type": "exact"
            }

        selected = best_products[0]

        # Check whether a generic product has specific variants.
        variants = _generic_product_variants(
            selected,
            products,
            normalized_text
        )

        if variants:
            return {
                "status": "AMBIGUOUS",
                "product": None,
                "candidates": variants,
                "match_type": "generic"
            }

        return {
            "status": "FOUND",
            "product": selected,
            "candidates": [selected],
            "match_type": "exact"
        }

    # Second: conservative fuzzy matching.
    fuzzy_candidates = []

    for product in products:

        score = max(
            (
                _fuzzy_score(text, name)
                for name in _product_names(product)
            ),
            default=0.0
        )

        if score >= FUZZY_THRESHOLD:
            fuzzy_candidates.append(
                (product, score)
            )

    fuzzy_candidates.sort(
        key=lambda item: item[1],
        reverse=True
    )

    if not fuzzy_candidates:
        return {
            "status": "NOT_FOUND",
            "product": None,
            "candidates": [],
            "match_type": None
        }

    # If two products have similar scores, don't guess.
    if (
        len(fuzzy_candidates) > 1
        and fuzzy_candidates[0][1] - fuzzy_candidates[1][1]
        < FUZZY_MIN_MARGIN
    ):

        close_matches = [
            product
            for product, score in fuzzy_candidates
            if fuzzy_candidates[0][1] - score < FUZZY_MIN_MARGIN
        ]

        return {
            "status": "AMBIGUOUS",
            "product": None,
            "candidates": close_matches,
            "match_type": "fuzzy"
        }

    selected = fuzzy_candidates[0][0]

    variants = _generic_product_variants(
        selected,
        products,
        normalized_text
    )

    if variants:
        return {
            "status": "AMBIGUOUS",
            "product": None,
            "candidates": variants,
            "match_type": "generic"
        }

    return {
        "status": "FOUND",
        "product": selected,
        "candidates": [selected],
        "match_type": "fuzzy"
    }


def find_product(text, products):
    """Backward-compatible helper."""

    return find_product_match(text, products)["product"]


def find_customer(text, customers):
    normalized_text = normalize(text)

    matches = []

    for customer in customers:
        customer_name = normalize(customer.name)

        if customer_name and re.search(
            rf"(?<!\w){re.escape(customer_name)}(?!\w)",
            normalized_text
        ):
            matches.append(customer)

    if not matches:
        return None

    matches.sort(
        key=lambda customer: len(normalize(customer.name)),
        reverse=True
    )

    if (
        len(matches) > 1
        and len(normalize(matches[0].name))
        == len(normalize(matches[1].name))
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

    product_match = find_product_match(
        normalized_text,
        products
    )

    quantity, unit = extract_quantity(normalized_text)

    return {
        "product": product_match["product"],
        "product_status": product_match["status"],
        "product_candidates": product_match["candidates"],
        "product_match_type": product_match["match_type"],
        "customer": find_customer(normalized_text, customers),
        "quantity": quantity,
        "unit": unit,
        "amount": extract_amount(normalized_text),
        "payment_method": extract_payment_method(normalized_text)
    }