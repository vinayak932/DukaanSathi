
from services.conversation import (
    start_product_clarification,
    process_clarification,
    start_sale_conversation,
    ask_next_question
)
from services.conversation_store import (
    get_active_conversation,
    save_conversation,
    finish_conversation
)
from services.sales_services import (
    record_confirmed_sale,
    record_customer_payment
)
from database.db import db
from database.models import Customer, User
from services.entity_extractor import (
    find_customer,
    extract_amount,
    extract_payment_method,
    normalize
)
from services.nlu_service import understand_user_message
from services.product_conversation import (
    start_product_conversation,
    process_product_reply
)
from services.product_service import create_product


def begin_product_clarification(user_id, shop_id, entities):
    """Start and persist a conversation when product matching is ambiguous."""

    if entities.get("product_status") != "AMBIGUOUS":
        raise ValueError(
            "Product clarification requires AMBIGUOUS status."
        )

    pending, response = start_product_clarification(entities)

    save_conversation(
        user_id=user_id,
        shop_id=shop_id,
        state_data=pending
    )

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }


def _is_yes(text):
    return normalize(text) in {
        "yes", "y", "haan", "han", "ha", "ji",
        "bilkul", "kar do", "add kar do",
        "haan kar do", "haan add kar do",
        "हाँ", "हां", "जी", "बिल्कुल",
        "हाँ कर दो", "हां कर दो",
        "हाँ जोड़ दो", "हां जोड़ दो",
        "जी कर दो", "जी कर दीजिए"
    }


def _is_no(text):
    return normalize(text) in {
        "no", "n", "nahi", "nahin", "na",
        "mat karo", "rehne do",
        "नहीं", "नही", "ना",
        "नहीं करो", "नहीं रहने दो"
    }


def _cancel_product_creation(user_id, shop_id):
    """Cancel product creation and its original pending sale."""

    finish_conversation(
        user_id=user_id,
        shop_id=shop_id,
        status="cancelled"
    )

    return {
        "status": "CANCELLED",
        "pending": None,
        "response": "Theek hai, product addition aur pending sale cancel kar di."
    }


def _start_product_creation_from_sale(
    user_id,
    shop_id,
    reply,
    pending
):
    """Ask for permission and start product registration if approved."""

    if _is_no(reply):
        items = pending.get("items", [])
        index = pending.get("current_item_index", 0)

        if index < len(items):
            item = items[index]

            # Do not retain a product name that was not found.
            item["product_name"] = None
            item["product_status"] = "NOT_PROVIDED"
            item["product_id"] = None
            item["candidate_product_ids"] = []

        pending["awaiting"] = None

        products = []
        customers = []

        # The caller handles the normal continuation after this helper.
        return {
            "status": "DECLINED",
            "pending": pending,
            "response": "Theek hai. Koi existing product select kar sakte hain."
        }

    if not _is_yes(reply):
        return {
            "status": "NEEDS_CLARIFICATION",
            "pending": pending,
            "response": "Kya main ye product add kar doon? Haan ya nahi bataiye."
        }

    # Only an owner can create a product.
    user = User.query.filter_by(
        id=user_id,
        shop_id=shop_id
    ).first()

    if not user or user.role != "owner":
        return {
            "status": "PERMISSION_DENIED",
            "pending": pending,
            "response": (
                "Naya product sirf shop owner add kar sakta hai. "
                "Aap kisi existing product ko select kar sakte hain."
            )
        }

    items = pending.get("items", [])
    index = pending.get("current_item_index", 0)

    if index >= len(items):
        return {
            "status": "ERROR",
            "pending": pending,
            "response": "Pending product details nahi mil paayi."
        }

    item = items[index]
    product_name = item.get("product_name")

    if not product_name:
        return {
            "status": "ERROR",
            "pending": pending,
            "response": "Product ka naam nahi mila. Dobara bataiye."
        }

    product_pending, response = start_product_conversation(
        product_name=product_name,
        unit=item.get("unit"),
        original_sale=pending
    )

    save_conversation(
        user_id=user_id,
        shop_id=shop_id,
        state_data=product_pending
    )

    return {
        "status": "CONTINUE",
        "pending": product_pending,
        "response": response
    }


def handle_product_creation_reply(
    user_id,
    shop_id,
    reply,
    pending,
    products,
    customers
):
    """Handle product registration and resume the original sale."""

    answer = normalize(reply)

    cancel_phrases = {
        "cancel", "cancel karo", "cancel kar do",
        "radd karo", "radd kar do", "stop",
        "रद्द करो", "रद्द कर दो",
        "कैंसल", "कैंसिल", "कैंसिल कर दो",
        "छोड़ दो", "छोड़ दो", "रहने दो"
    }

    if answer in cancel_phrases:
        return _cancel_product_creation(user_id, shop_id)

    # Step 1: Product creation details are being collected.
    result = process_product_reply(
        reply=reply,
        pending=pending
    )

    if result["status"] != "READY_TO_CREATE":
        save_conversation(
            user_id=user_id,
            shop_id=shop_id,
            state_data=result["pending"]
        )
        return result

    # Step 2: Verify owner permission again before database write.
    user = User.query.filter_by(
        id=user_id,
        shop_id=shop_id
    ).first()

    if not user or user.role != "owner":
        return {
            "status": "PERMISSION_DENIED",
            "pending": pending,
            "response": "Sirf shop owner naya product add kar sakta hai."
        }

    try:
        new_product = result["pending"]["new_product"]

        # Step 3: Create product using the existing service.
        product = create_product(
            user=user,
            name=new_product["name"],
            cost_price=new_product["cost_price"],
            selling_price=new_product["selling_price"],
            unit=new_product["unit"],
            stock_quantity=new_product["stock_quantity"]
        )

        # Step 4: Restore the original pending sale.
        original_sale = result["pending"].get("original_sale")

        if not original_sale:
            finish_conversation(
                user_id=user_id,
                shop_id=shop_id,
                status="completed"
            )

            return {
                "status": "PRODUCT_CREATED",
                "response": (
                    f"{product.name} inventory mein successfully add ho gaya."
                )
            }

        items = original_sale.get("items", [])
        index = original_sale.get("current_item_index", 0)

        if index >= len(items):
            finish_conversation(
                user_id=user_id,
                shop_id=shop_id,
                status="completed"
            )

            return {
                "status": "PRODUCT_CREATED",
                "response": (
                    f"{product.name} add ho gaya, "
                    "lekin original sale state restore nahi ho paayi."
                )
            }

        item = items[index]

        item["product_id"] = product.id
        item["product_name"] = product.name
        item["product_status"] = "FOUND"
        item["unit"] = product.unit
        item["candidate_product_ids"] = []

        original_sale["awaiting"] = None

        # Include the new product in the current inventory list.
        products.append(product)

        # Step 5: Continue the original sale.
        original_sale, response = ask_next_question(
            original_sale,
            products,
            customers
        )

        save_conversation(
            user_id=user_id,
            shop_id=shop_id,
            state_data=original_sale
        )

        if original_sale.get("awaiting") == "ready_to_record":
            return finalize_confirmed_sale(user_id, shop_id)

        return {
            "status": "PRODUCT_CREATED",
            "pending": original_sale,
            "response": (
                f"{product.name} successfully add ho gaya. "
                f"{response}"
            )
        }

    except (ValueError, PermissionError) as error:
        # Keep the product-registration conversation available
        # so the shopkeeper can correct the details.
        save_conversation(
            user_id=user_id,
            shop_id=shop_id,
            state_data=result["pending"]
        )

        return {
            "status": "ERROR",
            "pending": result["pending"],
            "response": str(error)
        }

    except Exception:
        db.session.rollback()

        save_conversation(
            user_id=user_id,
            shop_id=shop_id,
            state_data=result["pending"]
        )

        return {
            "status": "ERROR",
            "pending": result["pending"],
            "response": (
                "Product add nahi ho paaya. "
                "Kripya dobara koshish karein."
            )
        }


def handle_conversation_reply(
    user_id,
    shop_id,
    reply,
    products,
    customers
):
    pending = get_active_conversation(user_id, shop_id)

    if pending is None:
        return {
            "status": "NO_PENDING",
            "pending": None,
            "response": "Abhi koi transaction pending nahi hai."
        }

    # Product-registration conversation takes priority.
    if pending.get("workflow") == "product_creation":
        return handle_product_creation_reply(
            user_id=user_id,
            shop_id=shop_id,
            reply=reply,
            pending=pending,
            products=products,
            customers=customers
        )

    # Handle the consent question before normal sale clarification.
    if pending.get("awaiting") == "add_product_consent":
        result = _start_product_creation_from_sale(
            user_id=user_id,
            shop_id=shop_id,
            reply=reply,
            pending=pending
        )

        if result["status"] == "DECLINED":
            pending = result["pending"]

            pending, response = ask_next_question(
                pending,
                products,
                customers
            )

            save_conversation(
                user_id=user_id,
                shop_id=shop_id,
                state_data=pending
            )

            return {
                "status": "CONTINUE",
                "pending": pending,
                "response": "Theek hai. " + response
            }

        return result

    result = process_clarification(
        reply=reply,
        pending=pending,
        products=products,
        customers=customers
    )

    result_status = result["status"]

    # Create a customer only after explicit approval.
    if result_status == "CUSTOMER_CREATION_APPROVED":
        customer_name = (
            pending.get("customer_name") or ""
        ).strip()

        if not customer_name:
            return {
                "status": "ERROR",
                "pending": pending,
                "response": (
                    "Customer ka naam nahi mila. "
                    "Kripya naam dobara bataiye."
                )
            }

        try:
            customer = Customer.query.filter(
                Customer.shop_id == shop_id,
                db.func.lower(Customer.name) == customer_name.lower()
            ).first()

            if customer is None:
                customer = Customer(
                    name=customer_name,
                    phone=None,
                    shop_id=shop_id
                )
                db.session.add(customer)
                db.session.commit()

            pending["customer_id"] = customer.id
            pending.pop("customer_name", None)

            customers = list(customers)

            if all(
                existing.id != customer.id
                for existing in customers
            ):
                customers.append(customer)

            pending, response = ask_next_question(
                pending,
                products,
                customers
            )

            save_conversation(
                user_id,
                shop_id,
                pending
            )

            if pending.get("awaiting") == "ready_to_record":
                return finalize_confirmed_sale(user_id, shop_id)

            return {
                "status": "CONTINUE",
                "pending": pending,
                "response": response
            }

        except Exception:
            db.session.rollback()

            return {
                "status": "ERROR",
                "pending": pending,
                "response": (
                    "Customer add nahi ho paaya. "
                    "Kripya dobara koshish karein."
                )
            }

    if result_status == "CANCELLED":
        finish_conversation(
            user_id,
            shop_id,
            status="cancelled"
        )
        return result

    updated_pending = result.get("pending")

    if updated_pending is not None:
        save_conversation(
            user_id,
            shop_id,
            updated_pending
        )

    if result_status == "READY_TO_RECORD":
        return finalize_confirmed_sale(user_id, shop_id)

    return result


def complete_user_conversation(user_id, shop_id):
    """Complete only after the actual database transaction commits."""

    return finish_conversation(
        user_id=user_id,
        shop_id=shop_id,
        status="completed"
    )


def cancel_user_conversation(user_id, shop_id):
    """Explicitly cancel the user's active conversation."""

    return finish_conversation(
        user_id=user_id,
        shop_id=shop_id,
        status="cancelled"
    )


def finalize_confirmed_sale(user_id, shop_id):
    """Save a sale and complete the conversation after successful commit."""

    pending = get_active_conversation(user_id, shop_id)

    if pending is None:
        return {
            "status": "NO_PENDING",
            "response": "Abhi koi transaction pending nahi hai."
        }

    try:
        sale = record_confirmed_sale(
            user_id=user_id,
            shop_id=shop_id,
            pending=pending
        )

        finish_conversation(
            user_id,
            shop_id,
            status="completed"
        )

        return {
            "status": "COMPLETED",
            "sale_id": sale.id,
            "total_amount": str(sale.total_amount),
            "response": (
                f"Sale record ho gayi! "
                f"Kul ₹{sale.total_amount}."
            )
        }

    except ValueError as error:
        return {
            "status": "ERROR",
            "response": str(error)
        }

    except Exception:
        db.session.rollback()

        return {
            "status": "ERROR",
            "response": (
                "Sale record nahi ho paayi. "
                "Kripya dobara koshish karein."
            )
        }


def begin_sale(user_id, shop_id, entities, products, customers):
    """Start a sale and record it if all required information is available."""

    pending = start_sale_conversation(entities)

    pending, response = ask_next_question(
        pending,
        products,
        customers
    )

    save_conversation(
        user_id,
        shop_id,
        pending
    )

    if pending.get("awaiting") == "ready_to_record":
        return finalize_confirmed_sale(user_id, shop_id)

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }


def _is_full_settlement(text):
    normalized = normalize(text)

    phrases = [
        "clear",
        "settle",
        "क्लियर",
        "सेटल",
        "चुकता",
        "पूरा उधार",
        "सारा उधार",
        "पूरा बकाया",
        "सारा बकाया",
        "पूरा हिसाब",
        "poora udhaar",
        "saara udhaar"
    ]

    return any(phrase in normalized for phrase in phrases)


def _payment_question(pending):
    if not pending.get("customer_id"):
        pending["awaiting"] = "customer"
        return "Kis customer ne udhaar ke paise wapas diye?"

    if pending.get("amount") is None:
        pending["awaiting"] = "amount"
        return (
            f"{pending['customer_name']} se kitne rupaye mile?"
        )

    if pending.get("payment_method") is None:
        pending["awaiting"] = "payment_method"
        return (
            "Paise cash mein mile ya UPI se?"
        )

    pending["awaiting"] = "ready_to_record"
    return None


def begin_payment_conversation(
    user_id,
    shop_id,
    transcript,
    entities,
    customers
):
    customer = find_customer(transcript, customers)

    customer_name = entities.get("customer")

    if customer is None and customer_name:
        customer = find_customer(customer_name, customers)

    amount = extract_amount(transcript)

    if amount is None:
        amount = entities.get("amount")

    payment_method = extract_payment_method(transcript)

    if payment_method not in ("cash", "upi"):
        payment_method = entities.get("payment_method")

    if payment_method not in ("cash", "upi"):
        payment_method = None

    pending = {
        "type": "customer_payment",
        "customer_id": customer.id if customer else None,
        "customer_name": customer.name if customer else customer_name,
        "amount": str(amount) if amount is not None else None,
        "payment_method": payment_method,
        "awaiting": None
    }

    if (
        customer is not None
        and amount is None
        and _is_full_settlement(transcript)
    ):
        pending["amount"] = str(
            customer.outstanding_balance or 0
        )

    response = _payment_question(pending)

    save_conversation(
        user_id=user_id,
        shop_id=shop_id,
        state_data=pending
    )

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }


def handle_payment_reply(
    user_id,
    shop_id,
    reply,
    customers
):
    pending = get_active_conversation(user_id, shop_id)

    if pending is None or pending.get("type") != "customer_payment":
        return {
            "status": "NO_PENDING",
            "response": "Koi repayment conversation pending nahi hai."
        }

    # Ask Groq to interpret the reply using saved context.
    nlu_result = understand_user_message(
        reply,
        context=pending
    )

    entities = nlu_result.get("entities") or {}

    # 1. Resolve customer if still missing.
    if not pending.get("customer_id"):
        customer = find_customer(reply, customers)

        if customer is None:
            customer_name = entities.get("customer")

            if customer_name:
                customer = find_customer(
                    customer_name,
                    customers
                )

        if customer:
            pending["customer_id"] = customer.id
            pending["customer_name"] = customer.name

    # 2. Resolve amount.
    if pending.get("amount") is None:
        amount = extract_amount(reply)

        if amount is None:
            amount = entities.get("amount")

        if amount is not None:
            pending["amount"] = str(amount)

        elif (
            pending.get("customer_id")
            and _is_full_settlement(reply)
        ):
            customer = next(
                (
                    item for item in customers
                    if item.id == pending["customer_id"]
                ),
                None
            )

            if customer:
                pending["amount"] = str(
                    customer.outstanding_balance or 0
                )

    # 3. Resolve payment method.
    if pending.get("payment_method") is None:
        method = extract_payment_method(reply)

        if method not in ("cash", "upi"):
            method = entities.get("payment_method")

        if method in ("cash", "upi"):
            pending["payment_method"] = method

    # Ask for whatever is still missing.
    response = _payment_question(pending)

    if pending["awaiting"] != "ready_to_record":
        save_conversation(
            user_id,
            shop_id,
            pending
        )

        return {
            "status": "CONTINUE",
            "pending": pending,
            "response": response
        }

    # 4. Record only after all required information is available.
    try:
        customer = record_customer_payment(
            shop_id=shop_id,
            customer_id=pending["customer_id"],
            amount=pending["amount"],
            payment_method=pending["payment_method"]
        )

        finish_conversation(
            user_id=user_id,
            shop_id=shop_id,
            status="completed"
        )

        return {
            "status": "PAYMENT_RECORDED",
            "response": (
                f"{customer.name} se "
                f"₹{pending['amount']} "
                f"{pending['payment_method'].upper()} mein mile. "
                f"Ab unka baaki udhaar "
                f"₹{customer.outstanding_balance} hai."
            )
        }

    except ValueError as error:
        pending["amount"] = None
        pending["awaiting"] = "amount"

        save_conversation(
            user_id,
            shop_id,
            pending
        )

        return {
            "status": "PAYMENT_REJECTED",
            "pending": pending,
            "response": str(error)
        }

