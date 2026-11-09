from datetime import datetime, timedelta
from database.db import db
from database.models import ConversationState

CONVERSATION_TIMEOUT_MINUTES = 15

def get_active_conversation(user_id, shop_id):
    """
    Retrieve the user's active conversation.
    Expired conversations are automatically marked expired.
    """

    conversation = (
        ConversationState.query
        .filter_by(
            user_id=user_id,
            shop_id=shop_id,
            state="active"
        )
        .order_by(ConversationState.updated_at.desc())
        .first()
    )

    if conversation is None:
        return None

    now = datetime.utcnow()

    if conversation.expires_at <= now:
        conversation.state = "expired"
        db.session.commit()
        return None

    return conversation.state_data


def save_conversation(user_id, shop_id, state_data):
    """
    Create or update the user's active conversation.
    """

    if not isinstance(state_data, dict):
        raise ValueError("Conversation state must be a dictionary.")

    now = datetime.utcnow()

    conversation = (
        ConversationState.query
        .filter_by(
            user_id=user_id,
            shop_id=shop_id,
            state="active"
        )
        .order_by(ConversationState.updated_at.desc())
        .first()
    )

    if conversation is None:
        conversation = ConversationState(
            user_id=user_id,
            shop_id=shop_id,
            state_data=state_data,
            state="active",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(
                minutes=CONVERSATION_TIMEOUT_MINUTES
            )
        )

        db.session.add(conversation)

    else:
        conversation.state_data = state_data
        conversation.updated_at = now
        conversation.expires_at = now + timedelta(
            minutes=CONVERSATION_TIMEOUT_MINUTES
        )

    db.session.commit()

    return conversation


def finish_conversation(user_id, shop_id, status="completed"):
    """
    Mark the active conversation as completed or cancelled.
    """

    if status not in ["completed", "cancelled"]:
        raise ValueError("Invalid conversation status.")

    conversation = (
        ConversationState.query
        .filter_by(
            user_id=user_id,
            shop_id=shop_id,
            state="active"
        )
        .order_by(ConversationState.updated_at.desc())
        .first()
    )

    if conversation is None:
        return False

    conversation.state = status
    conversation.updated_at = datetime.utcnow()

    db.session.commit()

    return True
