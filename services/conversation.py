from decimal import Decimal, InvalidOperation
from services.entity_extractor import (
    normalize,
    normalize_product_phrase,
    extract_quantity,
    extract_payment_method,
    find_customer
)
from services.entity_extractor import find_product_match
from services.slot_extractor import extract_conversation_slots
from services.entity_resolver import normalize_unit
from services.conversation_interpreter import interpret_conversation_reply


def _make_item(
        product=None,
        quantity=None,
        unit=None,
        candidates=None,
        product_id=None,
        product_name=None,
        product_status=None
):
    return {
        "product_id": product_id or (
            product.id if product else None
        ),
        "product_name": (
                product_name or (product.name if product else None)
        ),
        "product_status": (
                product_status or ("FOUND" if product else "NOT_PROVIDED")
        ),
        "quantity": str(quantity) if quantity is not None else None,
        "unit": unit or (product.unit if product else None),
        "candidate_product_ids": [
            p.id for p in (candidates or [])
        ]
    }


def _get_items(pending):
    """Support both new multi-item and older single-item conversations."""

    if "items" in pending:
        return pending["items"]

    # Convert the old single-product pending structure.
    item = {
        "product_id": pending.get("product_id"),
        "quantity": pending.get("quantity"),
        "unit": pending.get("unit"),
        "candidate_product_ids": pending.get(
            "candidate_product_ids", []
        )
    }

    pending["items"] = [item]
    pending["current_item_index"] = 0

    return pending["items"]


def start_sale_conversation(entities):
    """
    Start a sale using already resolved entities.
    Supports both multi-item and legacy single-item formats.
    """

    pending_items = []
    raw_items = entities.get("items")

    if raw_items:
        for raw in raw_items:
            pending_items.append(
                _make_item(
                    product=raw.get("product"),
                    product_id=raw.get("product_id"),
                    quantity=raw.get("quantity"),
                    unit=raw.get("unit"),
                    candidates=raw.get("product_candidates"),
                    product_name=raw.get("product_name"),
                    product_status=raw.get("product_status")
                )
            )

    else:
        pending_items.append(
            _make_item(
                product=entities.get("product"),
                quantity=entities.get("quantity"),
                unit=entities.get("unit"),
                candidates=entities.get("product_candidates")
            )
        )

    pending = {
        "action": "record_sale",
        "awaiting": None,
        "items": pending_items,
        "current_item_index": 0,
        "customer_id": (
            entities["customer"].id
            if entities.get("customer") else None
        ),
        "customer_name": (
                entities.get("customer_name")
                or (
                    entities.get("customer")
                    if isinstance(entities.get("customer"), str)
                    else None
                )
        ),
        "payment_method": entities.get("payment_method"),
        "amount": (
            str(entities["amount"])
            if entities.get("amount") is not None else None
        )
    }

    return pending


def start_product_clarification(entities):
    """Start a sale conversation when product matching is ambiguous."""

    pending = start_sale_conversation(entities)
    pending["awaiting"] = "product"

    # Candidate products may be attached to the top-level entity
    # (legacy format) or to the first item (multi-item format).
    candidates = entities.get("product_candidates", [])
    if not candidates:
        raw_items = entities.get("items") or []
        if raw_items:
            candidates = raw_items[0].get("product_candidates", [])

    names = [product.name for product in candidates]
    response = (
        f"Kaunsa product? {', '.join(names)} mein se bataiye."
        if names else "Kaunsa product chahiye?"
    )

    return pending, response


def resolve_product_clarification(reply, pending, products):
    """Resolve a pending product selection."""

    if not pending or pending.get("awaiting") != "product":
        return {
            "status": "NO_PENDING_QUESTION",
            "pending": pending,
            "response": "Abhi koi product selection pending nahi hai."
        }

    items = _get_items(pending)
    index = pending.get("current_item_index", 0)

    if index >= len(items):
        return {
            "status": "ERROR",
            "pending": pending,
            "response": "Product selection state invalid hai."
        }

    item = items[index]

    candidate_ids = set(item.get("candidate_product_ids", []))

    candidates = [
        p for p in products if p.id in candidate_ids
    ]

    answer = normalize_product_phrase(reply)
    selected = None

    # Allow selection by candidate number.
    if answer.isdigit():
        number = int(answer)

        if 1 <= number <= len(candidates):
            selected = candidates[number - 1]

    # Allow selection by product name or alias.
    if selected is None:
        matches = []

        search_products = candidates if candidates else products

        for product in search_products:
            names = [product.name]
            names.extend(alias.alias for alias in product.aliases)

            for name in names:
                candidate_name = normalize_product_phrase(name)

                if (
                        answer == candidate_name
                        or answer in candidate_name.split()
                ):
                    matches.append(product)
                    break

        if len(matches) == 1:
            selected = matches[0]

    if selected is None:
        names = ", ".join(p.name for p in candidates)

        response = (
            f"{names} mein se clearly bataiye."
            if names else
            f"{item.get('product_name', 'Product')} inventory mein nahi mila."
        )

        return {
            "status": "NOT_RESOLVED",
            "pending": pending,
            "response": response
        }

    item["product_id"] = selected.id
    item["product_name"] = selected.name
    item["product_status"] = "FOUND"
    item["unit"] = selected.unit

    return {
        "status": "RESOLVED",
        "product": selected,
        "pending": pending,
        "response": f"Theek hai, {selected.name}."
    }


def build_sale_summary(pending, products, customers):
    """Validate all sale items and calculate the total without saving."""

    items = _get_items(pending)

    validated_items = []
    required_stock = {}
    total = Decimal("0.00")

    product_lookup = {
        product.id: product for product in products
    }

    for index, item in enumerate(items):

        product = product_lookup.get(item.get("product_id"))

        if product is None:
            return None, "Product ab inventory mein nahi mil raha."

        try:
            quantity = Decimal(str(item["quantity"]))
            unit_price = Decimal(str(product.price))
            stock = Decimal(str(product.stock_quantity))

            if not quantity.is_finite() or quantity <= 0:
                return None, f"{product.name} ki quantity valid nahi hai."

        except (InvalidOperation, KeyError, TypeError):
            return None, f"{product.name} ki quantity valid nahi hai."

        requested_unit = item.get("unit") or product.unit

        if requested_unit.lower() != product.unit.lower():
            return None, (
                f"{product.name} ka stock {product.unit} mein hai. "
                f"Quantity bhi {product.unit} mein bataiye."
            )

        required_stock[product.id] = (
                required_stock.get(product.id, Decimal("0"))
                + quantity
        )

        line_total = (quantity * unit_price).quantize(
            Decimal("0.01")
        )

        item["unit"] = product.unit
        item["unit_price"] = str(unit_price)
        item["line_total"] = str(line_total)

        validated_items.append({
            "product": product,
            "quantity": quantity,
            "line_total": line_total
        })

        total += line_total

    # Validate combined stock if the same product occurs more than once.
    for product_id, quantity in required_stock.items():

        product = product_lookup[product_id]
        stock = Decimal(str(product.stock_quantity))

        if quantity > stock:
            return None, (
                f"Abhi {product.name} ka stock sirf "
                f"{stock} {product.unit} hai."
            )

    total = total.quantize(Decimal("0.01"))

    customer = next(
        (
            c for c in customers
            if c.id == pending.get("customer_id")
        ),
        None
    )

    pending["total_amount"] = str(total)

    payment_labels = {
        "cash": "Cash",
        "upi": "UPI",
        "udhaar": "Udhaar"
    }

    payment_label = payment_labels.get(
        pending.get("payment_method"),
        pending.get("payment_method")
    )

    summaries = []

    for item in validated_items:
        product = item["product"]

        summaries.append(
            f"{product.name}, {item['quantity']} "
            f"{product.unit} = ₹{item['line_total']}"
        )

    summary = " | ".join(summaries)

    if customer:
        summary = f"{customer.name} ko: {summary}"

    summary += f". Kul ₹{total}. Payment: {payment_label}."

    if pending.get("payment_method") == "udhaar":
        summary += " Ye rakam customer ke udhaar mein jode jayegi."

    return summary, None


def ask_next_question(pending, products, customers):
    """Ask only for missing information."""

    items = _get_items(pending)

    # Check every product and quantity.
    for index, item in enumerate(items):

        pending["current_item_index"] = index

        if not item.get("product_id"):

            # Check whether the product was searched but not found.
            if (
                item.get("product_status") == "NOT_FOUND"
                and item.get("product_name")
            ):
                pending["awaiting"] = "add_product_consent"

                return pending, (
                    f"{item['product_name']} inventory mein nahi hai. "
                    "Kya main ise add kar doon?"
                )

            # Otherwise, ask the user to identify the product.
            pending["awaiting"] = "product"

            product_lookup = {
                p.id: p for p in products
            }

            candidates = [
                product_lookup[pid]
                for pid in item.get("candidate_product_ids", [])
                if pid in product_lookup
            ]

            names = [p.name for p in candidates]

            if names:
                return pending, (
                    f"Kaunsa product? {', '.join(names)} "
                    f"mein se bataiye."
                )

            return pending, "Kaunsa product chahiye?"

        if not item.get("quantity"):
            pending["awaiting"] = "quantity"

            product = next(
                (p for p in products if p.id == item["product_id"]),
                None
            )

            name = product.name if product else "Is product"

            return pending, f"{name} kitni quantity diya?"

    # Payment method is required.
    if not pending.get("payment_method"):
        pending["awaiting"] = "payment_method"
        return pending, "Payment cash, UPI ya udhaar mein hua?"

    # If the shopkeeper explicitly mentioned a customer who
    # isn't in the shop's customer list, ask before creating them.
    if (
        pending.get("customer_name")
        and not pending.get("customer_id")
    ):
        pending["awaiting"] = "customer_creation"
        return pending, (
            f"{pending['customer_name']} naam ka customer nahi mila. "
            "Kya main naya customer add kar doon?"
        )

    # Udhaar always requires an identified customer.
    if (
        pending.get("payment_method") == "udhaar"
        and not pending.get("customer_id")
    ):
        pending["awaiting"] = "customer"
        return pending, "Kis customer ko udhaar diya?"

    # All information is present. Validate and prepare the sale.
    summary, error = build_sale_summary(
        pending, products, customers
    )

    if error:
        pending["awaiting"] = "quantity"
        return pending, error

    pending["awaiting"] = "ready_to_record"
    pending["sale_summary"] = summary

    return pending, summary


def _merge_sale_updates(reply, pending, products, customers):
    """
    Extract all information in the latest reply and merge it
    into the existing sale conversation.
    """

    updates = extract_conversation_slots(
        workflow="record_sale",
        reply=reply,
        current_state=pending
    )

    changed = False

    # Customer
    if updates.get("customer"):
        customer = find_customer(updates["customer"], customers)

        if customer:
            pending["customer_id"] = customer.id
            pending.pop("customer_name", None)
            changed = True
        else:
            pending["customer_name"] = updates["customer"]

    # Payment method
    if updates.get("payment_method"):
        pending["payment_method"] = updates["payment_method"]
        changed = True

    # Preserve explicitly extracted amount.
    if updates.get("amount") is not None:
        pending["amount"] = updates["amount"]
        changed = True

    items = _get_items(pending)

    # Product items
    for raw in updates.get("items", []):
        product_name = raw.get("product")

        if not product_name:
            continue

        match = find_product_match(str(product_name), products)

        product = match.get("product")
        candidates = match.get("candidates", [])

        # Locate the existing item if this product is already pending.
        target = None

        if product:
            target = next(
                (
                    item for item in items
                    if item.get("product_id") == product.id
                ),
                None
            )

        if target is None:
            from services.entity_extractor import normalize_product_phrase

            normalized_name = normalize_product_phrase(product_name)

            target = next(
                (
                    item for item in items
                    if item.get("product_name")
                       and normalize_product_phrase(
                    item["product_name"]
                ) == normalized_name
                ),
                None
            )

        if target is None:
            # If Chotu is already asking for a product, update
            # that unresolved item instead of creating a duplicate.
            current_index = pending.get("current_item_index", 0)

            if pending.get("awaiting") == "product" and current_index < len(items):
                current_item = items[current_index]

                if not current_item.get("product_id"):
                    target = current_item

            # Only create a new item if this is genuinely another product.
            if target is None:
                target = {
                    "product_id": None,
                    "product_name": str(product_name),
                    "product_status": match["status"],
                    "quantity": None,
                    "unit": None,
                    "candidate_product_ids": []
                }
                items.append(target)

        if product:
            target["product_id"] = product.id
            target["product_name"] = product.name
            target["product_status"] = "FOUND"
            target["unit"] = product.unit

        elif match["status"] == "AMBIGUOUS":
            target["product_status"] = "AMBIGUOUS"
            target["candidate_product_ids"] = [
                candidate.id for candidate in candidates
            ]

        else:
            target["product_status"] = match["status"]

        if raw.get("quantity") is not None:
            target["quantity"] = raw["quantity"]

        if raw.get("unit"):
            target["unit"] = normalize_unit(raw["unit"])

        changed = True

    return pending, changed


def process_clarification(reply, pending, products, customers):
    if not pending:
        return {
            "status": "NO_PENDING",
            "pending": None,
            "response": "Abhi koi transaction pending nahi hai."
        }

    awaiting = pending.get("awaiting")
    answer = normalize(reply)

    # Handle cancellation before processing any pending question.
    cancel_phrases = {
        # English
        "cancel",
        "cancel it",
        "cancel this",
        "ok cancel",
        "okay cancel",
        "ok cancel it",
        "okay cancel it",
        "cancel the sale",
        "cancel the transaction",
        "stop",

        # Roman Hindi
        "cancel karo",
        "cancel kar do",
        "chhod do",
        "chod do",
        "rehne do",
        "radd karo",
        "radd kar do",

        # Devanagari Hindi
        "कैंसल",
        "कैंसल कर दो",
        "रद्द करो",
        "रद्द कर दो",
        "छोड़ दो",
        "छोड़ दो",
        "रहने दो",
        "बंद करो",

        # Devanagari Hindi - कैंसिल
        "कैंसिल",
        "कैंसिल करो",
        "कैंसिल कर दो",
        "कैंसिल कर दे",
        "ऑर्डर कैंसिल",
        "ऑर्डर कैंसिल करो",
        "ऑर्डर कैंसिल कर दो",
        "ऑर्डर कैंसिल कर दे",
        "ऑर्डर को कैंसिल कर दो",
    }

    if answer in cancel_phrases:
        return {
            "status": "CANCELLED",
            "pending": None,
            "response": "Theek hai, transaction cancel kar diya."
        }

    # Customer creation is a consent step, not a transaction-cancel
    # step. Handle its yes/no answers before the general cancel words.
    if awaiting == "customer_creation":
        yes_words = {
            # English
            "yes", "y",

            # Roman Hindi
            "haan", "ha", "han", "ji",
            "bilkul", "kar do", "add kar do",
            "haan kar do", "haan add kar do",

            # Devanagari Hindi
            "हाँ", "हां", "जी", "बिल्कुल",
            "हाँ कर दो", "हां कर दो",
            "हाँ जोड़ दो", "हां जोड़ दो",
            "जी कर दो", "जी कर दीजिए",
        }

        no_words = {
            "nahi", "nahin", "na", "no", "n",
            "mat karo", "rehne do",
            "नहीं", "नही", "ना",
            "नहीं करो", "नहीं रहने दो",
        }

        if answer in yes_words:
            return {
                "status": "CUSTOMER_CREATION_APPROVED",
                "pending": pending,
                "response": "Theek hai, customer add kar raha hoon."
            }

        if answer in no_words:
            pending.pop("customer_name", None)

            if (
                    pending.get("payment_method") == "udhaar"
                    and not pending.get("customer_id")
            ):
                pending["awaiting"] = "customer"
                return {
                    "status": "CONTINUE",
                    "pending": pending,
                    "response": "Theek hai. Udhaar ke liye customer ka naam bataiye."
                }

            pending, response = ask_next_question(
                pending, products, customers
            )

            return {
                "status": (
                    "READY_TO_RECORD"
                    if pending.get("awaiting") == "ready_to_record"
                    else "CONTINUE"
                ),
                "pending": pending,
                "response": response
            }

        interpreted = interpret_conversation_reply(reply, pending)

        if interpreted["confidence"] in {"high", "medium"}:

            if interpreted["action"] == "approve":
                return {
                    "status": "CUSTOMER_CREATION_APPROVED",
                    "pending": pending,
                    "response": "Theek hai, customer add kar raha hoon."
                }

            if interpreted["action"] == "reject":
                pending.pop("customer_name", None)

                if (
                        pending.get("payment_method") == "udhaar"
                        and not pending.get("customer_id")
                ):
                    pending["awaiting"] = "customer"
                    return {
                        "status": "CONTINUE",
                        "pending": pending,
                        "response": "Theek hai. Udhaar ke liye customer ka naam bataiye."
                    }

                pending, response = ask_next_question(
                    pending, products, customers
                )

                return {
                    "status": (
                        "READY_TO_RECORD"
                        if pending.get("awaiting") == "ready_to_record"
                        else "CONTINUE"
                    ),
                    "pending": pending,
                    "response": response
                }

        return {
            "status": "NEEDS_CLARIFICATION",
            "pending": pending,
            "response": "Customer add kar doon? Haan ya nahi bataiye."
        }

    cancel_words = [
        "cancel", "cancel karo", "radd karo",
        "radd kar do", "nahi", "rehne do"
    ]

    if answer in cancel_words:
        return {
            "status": "CANCELLED",
            "pending": None,
            "response": "Theek hai, transaction cancel kar diya."
        }

    # Extract every available field from the reply.
    pending, changed = _merge_sale_updates(
        reply, pending, products, customers
    )

    if not changed:
        interpreted = interpret_conversation_reply(
            reply,
            pending
        )

        if (
            interpreted["action"] == "cancel"
            and interpreted["confidence"] in {"high", "medium"}
        ):
            return {
                "status": "CANCELLED",
                "pending": None,
                "response": "Theek hai, transaction cancel kar diya."
            }

    items = _get_items(pending)
    index = pending.get("current_item_index", 0)

    # Retain the existing product-selection mechanism when
    # the reply is a candidate number or product name.
    if awaiting == "product":
        item = items[index]

        if not item.get("product_id"):
            result = resolve_product_clarification(
                reply, pending, products
            )

            if result["status"] == "RESOLVED":
                changed = True

            elif not changed:
                return result

    # Fallback for quantity-only replies such as "2 kilo".
    elif awaiting == "quantity":
        item = items[index]

        if not item.get("quantity"):
            quantity, unit = extract_quantity(reply)

            if quantity is None:
                return {
                    "status": "NEEDS_CLARIFICATION",
                    "pending": pending,
                    "response": "Quantity dobara bataiye, jaise 2 kilo."
                }

            item["quantity"] = str(quantity)

            if unit:
                item["unit"] = unit

            changed = True

    # Fallback for payment-only replies.
    elif awaiting == "payment_method":
        if not pending.get("payment_method"):
            method = extract_payment_method(reply)

            if method is None:
                return {
                    "status": "NEEDS_CLARIFICATION",
                    "pending": pending,
                    "response": "Cash, UPI ya udhaar mein se bataiye."
                }

            pending["payment_method"] = method
            changed = True

    # Fallback for customer-only replies.
    elif awaiting == "customer":
        if not pending.get("customer_id"):
            customer = find_customer(reply, customers)

            if customer is None:
                return {
                    "status": "NEEDS_CLARIFICATION",
                    "pending": pending,
                    "response": (
                        "Customer nahi mila. Naam dobara bataiye "
                        "ya pehle customer add kijiye."
                    )
                }

            pending["customer_id"] = customer.id
            changed = True

    elif awaiting == "ready_to_record":
        return {
            "status": "READY_TO_RECORD",
            "pending": pending,
            "response": "Transaction details are ready."
        }

    # Ask only for the information still missing.
    pending, response = ask_next_question(
        pending, products, customers
    )

    if pending.get("awaiting") == "ready_to_record":
        return {
            "status": "READY_TO_RECORD",
            "pending": pending,
            "response": response
        }

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }
