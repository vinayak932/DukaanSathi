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
from services.sales_services import record_confirmed_sale


def begin_product_clarification(user_id, shop_id, entities):
    """
    Start and persist a conversation when product
    recognition is ambiguous.
    """

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

    result = process_clarification(
        reply=reply,
        pending=pending,
        products=products,
        customers=customers
    )

    result_status = result["status"]

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

    # Automatically save when all required information is ready.
    if result_status == "READY_TO_RECORD":
        return finalize_confirmed_sale(user_id, shop_id)

    return result

def complete_user_conversation(user_id, shop_id):
    """
    Call only after the actual database transaction
    has been successfully committed.
    """

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
    """
    Save a confirmed sale and complete the conversation
    only after the database commit succeeds.
    """

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

        # The sales service has committed successfully.
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
        return {
            "status": "ERROR",
            "response": (
                "Sale record nahi ho paayi. "
                "Kripya dobara koshish karein."
            )
        }


def begin_sale(user_id, shop_id, entities, products, customers):
    """
    Start a sale conversation.
    Automatically record it if all required information is available.
    """

    pending = start_sale_conversation(entities)

    pending, response = ask_next_question(
        pending,
        products,
        customers
    )

    save_conversation(user_id, shop_id, pending)

    if pending.get("awaiting") == "ready_to_record":
        return finalize_confirmed_sale(user_id, shop_id)

    return {
        "status": "CONTINUE",
        "pending": pending,
        "response": response
    }
