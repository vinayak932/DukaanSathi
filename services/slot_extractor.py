import json
from decimal import Decimal, InvalidOperation

from services.llm_service import client, MODEL


WORKFLOW_FIELDS = {
    "product_creation": {
        "product_name": "Product name, if explicitly mentioned",
        "unit": "Product unit",
        "cost_price": "Buying price",
        "selling_price": "Selling price",
        "stock_quantity": "Current opening stock",
    },
    "record_sale": {
        "customer": "Customer name",
        "payment_method": "cash, upi or udhaar",
        "amount": "Sale amount, if explicitly mentioned",
        "items": (
            "List of product items. Each item can contain "
            "product, quantity and unit."
        ),
    },
    "record_payment": {
        "customer": "Customer name",
        "amount": "Amount of repayment",
    },
}


def _validate_number(value, field_name):
    """Validate extracted numeric values without guessing."""
    if isinstance(value, bool):
        raise ValueError(f"Invalid numeric value for {field_name}.")

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid numeric value for {field_name}.")

    if not number.is_finite() or number < 0:
        raise ValueError(f"Invalid numeric value for {field_name}.")

    return str(number)


def extract_conversation_slots(
    workflow,
    reply,
    current_state=None
):
    """
    Extract every explicitly mentioned field from one reply.

    Does not modify conversation state or database records.
    Missing fields are omitted, never returned as updates with null.
    """

    if workflow not in WORKFLOW_FIELDS:
        raise ValueError(f"Unsupported workflow: {workflow}")

    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("Reply cannot be empty.")

    allowed_fields = WORKFLOW_FIELDS[workflow]

    system_prompt = f"""
You are Chotu's conversation information extractor.

Understand Hindi, Devanagari Hindi, Hinglish and English.

Active workflow: {workflow}

Allowed fields:
{json.dumps(allowed_fields, ensure_ascii=False)}

Existing conversation state:
{json.dumps(current_state or {}, ensure_ascii=False, default=str)}

Latest shopkeeper reply:
The latest reply is the ONLY source for new updates.
Existing state is context, not new information.

RULES:
1. Extract ALL fields explicitly mentioned in the latest reply.
2. Do not extract only the field Chotu last asked about.
3. Do not invent or assume missing values.
4. Do not return an update for a field not mentioned.
5. Never return null values as updates.
6. For product_creation, extract buying price, selling price,
   stock quantity, unit and product name independently.
7. For record_sale, extract every product separately.
8. For record_sale items, each item may contain product,
   quantity and unit. Include only explicitly mentioned values.
9. Payment method must be cash, upi or udhaar.
10. Recognise Hindi and Hinglish expressions.
11. If a value is unclear, omit it.
12. Do not calculate or infer financial values.

Return ONLY valid JSON in this format:

{{
    "updates": {{}}
}}
"""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": reply},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=600,
    )

    content = completion.choices[0].message.content

    if not content:
        raise RuntimeError("Groq returned an empty slot extraction.")

    result = json.loads(content)
    updates = result.get("updates")

    if not isinstance(updates, dict):
        raise ValueError("Invalid slot extraction response.")

    # Reject fields outside the active workflow.
    if not set(updates).issubset(allowed_fields):
        raise ValueError("Extractor returned unsupported fields.")

    validated = {}

    for field, value in updates.items():

        # Missing or uncertain information is not an update.
        if value is None:
            continue

        if field in {
            "cost_price",
            "selling_price",
            "stock_quantity",
            "amount",
        }:
            validated[field] = _validate_number(value, field)

        elif field == "payment_method":
            method = str(value).strip().lower()

            aliases = {
                "cash": "cash",
                "nagad": "cash",
                "नकद": "cash",
                "upi": "upi",
                "online": "upi",
                "udhaar": "udhaar",
                "उधार": "udhaar",
                "credit": "udhaar",
            }

            if method not in aliases:
                raise ValueError("Invalid payment method extracted.")

            validated[field] = aliases[method]

        elif field == "items":
            if not isinstance(value, list):
                raise ValueError("Sale items must be a list.")

            validated_items = []

            for item in value:
                if not isinstance(item, dict):
                    raise ValueError("Invalid sale item.")

                if not set(item).issubset(
                    {"product", "quantity", "unit"}
                ):
                    raise ValueError("Unsupported sale item field.")

                clean_item = {}

                for key, item_value in item.items():
                    if item_value is None:
                        continue

                    if key == "quantity":
                        clean_item[key] = _validate_number(
                            item_value, "quantity"
                        )
                    else:
                        if not isinstance(item_value, str):
                            raise ValueError(
                                f"Invalid {key} in sale item."
                            )
                        clean_item[key] = item_value.strip()

                if clean_item:
                    validated_items.append(clean_item)

            if validated_items:
                validated[field] = validated_items

        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Invalid value for {field}.")

            validated[field] = value.strip()

    return validated
