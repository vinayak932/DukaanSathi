import os
import json
import math

from dotenv import load_dotenv
from groq import Groq


load_dotenv()

MODEL = "openai/gpt-oss-20b"

ALLOWED_INTENTS = {
    "greeting",
    "record_sale",
    "record_payment",
    "query_records",
    "calculate",
    "unknown"
}

VALID_PAYMENT_METHODS = {"cash", "upi", "udhaar"}


def get_groq_client():
    """
    Create the Groq client only when a request is made.
    Missing API keys will not prevent Flask from starting.
    """
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing.")

    return Groq(
        api_key=api_key,
        timeout=15.0,
        max_retries=0
    )


def validate_result(result):
    if not isinstance(result, dict):
        raise ValueError("Groq response must be a JSON object.")

    if result.get("intent") not in ALLOWED_INTENTS:
        raise ValueError("Unsupported intent returned by Groq.")

    if result.get("confidence") not in {"high", "medium", "low"}:
        raise ValueError("Invalid confidence returned by Groq.")

    if not isinstance(result.get("entities"), dict):
        raise ValueError("Invalid entities returned by Groq.")

    if not isinstance(result.get("needs_clarification"), bool):
        raise ValueError("Invalid clarification flag.")

    if not isinstance(result.get("response"), (str, type(None))):
        raise ValueError("Invalid response.")

    if not isinstance(
        result.get("clarification_reason"),
        (str, type(None))
    ):
        raise ValueError("Invalid clarification reason.")

    entities = result["entities"]

    # Ensure the backend always receives the expected keys.
    entities.setdefault("customer", None)
    entities.setdefault("items", [])
    entities.setdefault("amount", None)
    entities.setdefault("payment_method", None)

    if not isinstance(entities["items"], list):
        raise ValueError("Entities.items must be a list.")

    for item in entities["items"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid product item.")

        for key in ("product", "quantity", "unit"):
            if key not in item:
                raise ValueError(f"Product item is missing {key}.")

        if not isinstance(item["product"], (str, type(None))):
            raise ValueError("Invalid product name.")

        if not isinstance(item["unit"], (str, type(None))):
            raise ValueError("Invalid product unit.")

        quantity = item["quantity"]

        if isinstance(quantity, bool):
            raise ValueError("Invalid product quantity.")

        if not isinstance(quantity, (int, float, str, type(None))):
            raise ValueError("Invalid product quantity.")

        if isinstance(quantity, float) and not math.isfinite(quantity):
            raise ValueError("Product quantity must be finite.")

        if isinstance(quantity, str) and quantity.strip():
            try:
                parsed_quantity = float(quantity)
                if not math.isfinite(parsed_quantity):
                    raise ValueError("Product quantity must be finite.")
            except ValueError:
                raise ValueError("Product quantity must be numeric.")

    for key in ("customer", "payment_method"):
        if not isinstance(entities[key], (str, type(None))):
            raise ValueError(f"Invalid {key}.")

    if entities["payment_method"] is not None:
        entities["payment_method"] = entities["payment_method"].lower().strip()

        if entities["payment_method"] not in VALID_PAYMENT_METHODS:
            raise ValueError("Unsupported payment method.")

    amount = entities["amount"]

    if isinstance(amount, bool):
        raise ValueError("Invalid amount.")

    if not isinstance(amount, (int, float, str, type(None))):
        raise ValueError("Invalid amount.")

    if isinstance(amount, float) and not math.isfinite(amount):
        raise ValueError("Amount must be finite.")

    if isinstance(amount, str) and amount.strip():
        try:
            parsed_amount = float(amount)
            if not math.isfinite(parsed_amount):
                raise ValueError("Amount must be finite.")
        except ValueError:
            raise ValueError("Amount must be numeric.")

    return result


def understand_message(text, context=None):

    if not text or not text.strip():
        raise ValueError("Message cannot be empty.")

    system_prompt = """
You are Chotu, the language understanding engine for an
Indian shopkeeper's voice assistant.

Understand natural Hindi, Devanagari Hindi, Hinglish and English.

Classify every message into exactly one intent:
- greeting
- record_sale
- record_payment
- query_records
- calculate
- unknown

IMPORTANT RULES:

1. Understand meaning, not just keywords.
2. A sale means goods are being given to a customer.
3. A payment means existing udhaar is being repaid.
4. Never confuse giving goods on credit with receiving repayment.
5. Casual conversation is not a shop transaction.
6. Never invent products, customers, quantities or amounts.
7. Never claim an operation has been completed.
8. Never assume missing information.
9. Use unknown for unrelated or unclear requests.

PAYMENT METHOD DETECTION:

- Cash, nagad, नकद -> "cash"
- UPI, online, PhonePe, Google Pay, GPay, Paytm -> "upi"
- Udhaar, उधार, उधारी, credit, on credit -> "udhaar"
- If the payment type is not mentioned, use null.

IMPORTANT DISTINCTION:

- "उधार दे दिया" means a credit SALE.
- "पुराना उधार वापस किया" means a REPAYMENT.

Credit sale:
intent = record_sale
payment_method = "udhaar"

Repayment:
intent = record_payment

Never classify a credit sale as repayment merely because
the word udhaar appears.

MULTI-PRODUCT EXTRACTION:

1. Extract EVERY product mentioned in a transaction.
2. Store each product as a separate object inside "items".
3. Extract the quantity and unit belonging to that product.
4. Preserve the spoken product name.
5. Do not combine different products into one item.
6. Do not invent a quantity or unit.
7. Missing quantity or unit must be null.
8. Missing customer must be null.
9. For non-sale messages, items must be an empty list.

CONVERSATION BEHAVIOUR:

Greeting:
- intent = greeting
- Give a friendly Hindi/Hinglish response.

Casual conversation:
- intent = unknown
- needs_clarification = false when meaning is clear.
- Give a short natural response.

Ambiguous shop command:
- intent = unknown
- needs_clarification = true.
- Ask a specific clarification question.

Sale transaction:
- intent = record_sale.
- Extract every product into items.
- Extract customer and payment method when available.
- Missing information must be null.
- Never claim the transaction is completed.
- Python handles validation and confirmation.

Customer repayment:
- intent = record_payment.
- This means money was received against previously outstanding udhaar.
- Extract customer and repayment amount when available.
- Payment method must be cash or upi only when explicitly mentioned.
- Do not assume the full outstanding balance was paid.

Examples:

"Mukesh ne 500 rupaye wapas diye"
-> record_payment, customer = "Mukesh", amount = 500

"Ramesh se 200 UPI mile"
-> record_payment, customer = "Ramesh",
   amount = 200, payment_method = "upi"

"Suresh ka udhaar clear kar do"
-> record_payment, customer = "Suresh", amount = null

"Mukesh ko 500 rupaye ka samaan diya"
-> record_sale, NOT record_payment

"Mukesh ko 500 rupaye udhaar diye"
-> record_sale, payment_method = "udhaar"

Records query and calculation:
- Identify the request.
- Never invent financial results.
- Let Python retrieve or calculate actual data.

Return ONLY valid JSON using this structure:

{
    "intent": "unknown",
    "confidence": "low",
    "entities": {
        "customer": null,
        "items": [],
        "amount": null,
        "payment_method": null
    },
    "needs_clarification": false,
    "clarification_reason": null,
    "response": null
}

ADDITIONAL REQUIREMENTS:

- Every item must contain product, quantity and unit.
- Product and unit must be strings or null.
- Quantity must be a number, numeric string or null.
- Do not create empty product items.
- Confidence must be high, medium or low.
- needs_clarification must be a boolean.
- Use natural Hindi/Hinglish for response.
- For casual conversation, response should not be null.
- For transaction requests, response must be null.
- Return no Markdown or text outside JSON.
"""

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    if context:
        messages.append({
            "role": "system",
            "content": f"""
You are handling an ongoing customer repayment conversation.

Previously collected information:
{json.dumps(context, ensure_ascii=False)}

Interpret the latest message as a reply to this pending repayment.

Rules:
1. Return intent = "record_payment".
2. Extract only information supplied or clearly implied by the latest reply.
3. Do not replace previously known information with null.
4. If the user provides only an amount, extract the amount.
5. If the user provides only a payment method, extract that method.
6. If the user provides a customer name, extract that customer.
7. Do not invent missing information.
8. Do not assume full settlement unless explicitly requested.
9. Do not claim repayment has been completed.
10. Return the normal JSON response structure.
"""
        })

    messages.append({
        "role": "user",
        "content": text
    })

    client = get_groq_client()

    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=1200
    )

    content = completion.choices[0].message.content

    if not content:
        raise RuntimeError("Groq returned an empty response.")

    result = json.loads(content)

    return validate_result(result)

