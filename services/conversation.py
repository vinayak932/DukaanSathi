
from services.entity_extractor import (
    normalize,
    normalize_product_phrase,
    extract_quantity,
    extract_payment_method,
    find_customer
)


def start_product_clarification(entities):
    candidates = entities.get("product_candidates", [])

    pending = {
        "action": "record_sale",
        "awaiting": "product",
        "quantity": (
            str(entities["quantity"])
            if entities.get("quantity") is not None else None
        ),
        "unit": entities.get("unit"),
        "amount": (
            str(entities["amount"])
            if entities.get("amount") is not None else None
        ),
        "customer_id": (
            entities["customer"].id
            if entities.get("customer") else None
        ),
        "payment_method": entities.get("payment_method"),
        "candidate_product_ids": [
            product.id for product in candidates
        ]
    }

    names = [product.name for product in candidates]

    response = (
        f"Kaunsa product? {', '.join(names)} mein se bataiye."
        if names else "Kaunsa product chahiye?"
    )

    return pending, response


def resolve_product_clarification(reply, pending, products):
    if not pending or pending.get("awaiting") != "product":
        return {
            "status": "NO_PENDING_QUESTION",
            "pending": None,
            "response": "Abhi koi clarification pending nahi hai."
        }

    candidate_ids = set(pending["candidate_product_ids"])

    candidates = [
        p for p in products if p.id in candidate_ids
    ]

    answer = normalize_product_phrase(reply)

    # Match option number: 1, 2, 3
    if answer.isdigit():
        number = int(answer)

        if 1 <= number <= len(candidates):
            selected = candidates[number - 1]
            updated = {**pending, "product_id": selected.id}
            return {
                "status": "RESOLVED",
                "product": selected,
                "pending": updated,
                "response": f"Theek hai, {selected.name}."
            }

    matches = []

    for product in candidates:
        names = [product.name]
        names.extend(a.alias for a in product.aliases)

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
        updated = {**pending, "product_id": selected.id}

        return {
            "status": "RESOLVED",
            "product": selected,
            "pending": updated,
            "response": f"Theek hai, {selected.name}."
        }

    names = ", ".join(p.name for p in candidates)

    return {
        "status": "NOT_RESOLVED",
        "product": None,
        "pending": pending,
        "response": f"{names} mein se clearly bataiye."
    }


def ask_next_question(pending):
    if not pending.get("product_id"):
        pending["awaiting"] = "product"
        return pending, "Kaunsa product diya?"

    if not pending.get("quantity"):
        pending["awaiting"] = "quantity"
        return pending, "Kitni quantity di?"

    if not pending.get("payment_method"):
        pending["awaiting"] = "payment_method"
        return pending, "Payment cash, UPI ya udhaar mein hua?"

    if (
        pending["payment_method"] == "udhaar"
        and not pending.get("customer_id")
    ):
        pending["awaiting"] = "customer"
        return pending, "Kis customer ko udhaar diya?"

    pending["awaiting"] = "confirmation"

    return pending, (
        "Sale confirm karne ke liye details check kar lijiye."
    )


def process_clarification(reply, pending, products, customers):
    if not pending:
        return {
            "status": "NO_PENDING",
            "pending": None,
            "response": "Abhi koi transaction pending nahi hai."
        }

    awaiting = pending.get("awaiting")
    answer = normalize(reply)

    if answer in ["cancel", "cancel karo", "radd karo", "nahi"]:
        return {
            "status": "CANCELLED",
            "pending": None,
            "response": "Theek hai, transaction cancel kar diya."
        }

    if awaiting == "product":
        result = resolve_product_clarification(
            reply, pending, products
        )

        if result["status"] != "RESOLVED":
            return result

        pending = result["pending"]
        pending["awaiting"] = "next_step"

    elif awaiting == "quantity":
        quantity, unit = extract_quantity(reply)

        if quantity is None:
            return {
                "status": "NEEDS_CLARIFICATION",
                "pending": pending,
                "response": "Quantity dobara bataiye, jaise 2 kilo."
            }

        pending["quantity"] = str(quantity)
        pending["unit"] = unit or pending.get("unit")

    elif awaiting == "payment_method":
        method = extract_payment_method(reply)

        if method is None:
            return {
                "status": "NEEDS_CLARIFICATION",
                "pending": pending,
                "response": "Cash, UPI ya udhaar mein se bataiye."
            }

        pending["payment_method"] = method

    elif awaiting == "customer":
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

    elif awaiting == "confirmation":
        if answer in ["haan", "yes", "confirm", "kar do", "haan karo"]:
            return {
                "status": "READY_TO_RECORD",
                "pending": pending,
                "response": "Confirmation mil gaya."
            }

        return {
            "status": "NEEDS_CLARIFICATION",
            "pending": pending,
            "response": "Sale record karne ke liye haan ya cancel boliye."
        }

    pending, response = ask_next_question(pending)

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }
