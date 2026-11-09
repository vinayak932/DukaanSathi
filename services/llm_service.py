
import os
import json

from dotenv import load_dotenv
from groq import Groq


load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("GROQ_API_KEY is missing from .env")

client = Groq(api_key=API_KEY)

MODEL = "openai/gpt-oss-20b"

ALLOWED_INTENTS = {
    "greeting",
    "record_sale",
    "record_payment",
    "query_records",
    "calculate",
    "unknown"
}


def understand_message(text):

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


IMPORTANT RULES:

1. Understand the meaning, not just keywords.
2. A sale means goods are being given to a customer.
3. A payment means an existing udhaar is being repaid.
4. Never confuse giving goods on credit with receiving repayment.
5. Casual conversation is not a shop transaction.
6. Never invent products, customers, quantities or amounts.
7. Never claim an operation has been completed.
8. Never assume missing information.
9. Use unknown for unrelated or unclear requests.

PAYMENT METHOD DETECTION — VERY IMPORTANT:

1. If the shopkeeper explicitly says cash, nagad, नकद:
   payment_method = "cash"

2. If the shopkeeper explicitly says UPI, online, PhonePe,
   Google Pay, GPay or Paytm:
   payment_method = "upi"

3. If the shopkeeper says udhaar, उधार, उधारी,
   credit, on credit, baad mein paise denge,
   or paisa baad mein lega:
   payment_method = "udhaar"

4. Hindi and Hinglish expressions must be recognised.
   For example:
   - "उधार दे दिया"
   - "उधार में लिख दो"
   - "udhaar pe de diya"
   - "credit par diya"
   - "baad mein paise dega"

5. Do not leave payment_method null when the payment
   type is explicitly mentioned or clearly implied.

6. If the payment type is genuinely not mentioned,
   payment_method = null.

7. IMPORTANT: "उधार दे दिया" means a credit SALE.
   "पुराना उधार वापस किया" means a REPAYMENT.
   These must have different intents:
   - Credit sale: record_sale, payment_method = "udhaar"
   - Repayment: record_payment

8. Never classify a credit sale as record_payment
   merely because it contains the word "udhaar".


MULTI-PRODUCT EXTRACTION:

1. Extract EVERY product mentioned in a transaction.
2. Store each product as a separate object inside "items".
3. Extract the quantity and unit belonging to that product.
4. Preserve the spoken product name in Hindi, Hinglish or English.
5. Do not combine different products into one item.
6. Do not invent a quantity if it was not spoken.
7. If the product is mentioned but quantity is missing,
   set quantity to null.
8. If quantity is mentioned but unit is unclear,
   set unit to null.
9. If the customer is not mentioned, customer = null.
10. If payment method is not mentioned, payment_method = null.

CONVERSATION BEHAVIOUR:

A. Greeting:
- intent = greeting
- Give a friendly, natural Hindi/Hinglish response.

B. Casual conversation:
- intent = unknown
- confidence = high if the meaning is clear.
- needs_clarification = false.
- Give a short, natural conversational response.

C. Ambiguous shop command:
- intent = unknown
- needs_clarification = true.
- Ask a specific clarification question.

D. Sale transaction:
- intent = record_sale.
- Extract all mentioned products into items.
- Extract customer and payment method when available.
- Missing entities must be null.
- Do not claim that the transaction is completed.
- Let Python handle validation and missing information.

E. Payment:
- intent = record_payment.
- Extract customer and amount.
- Do not confuse a repayment with a credit sale.

F. Records query and calculation:
- Identify the request.
- Never invent financial results.
- Let Python retrieve or calculate actual data.

RETURN ONLY VALID JSON USING THIS STRUCTURE:

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
- For non-sale messages, items should be an empty list.
- confidence must be high, medium or low.
- needs_clarification must be a boolean.
- Use natural Hindi/Hinglish for response.
- For casual conversation, response should not be null.
- For transaction requests, response must be null.
- Return no Markdown or text outside JSON.
"""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=1200
    )

    content = completion.choices[0].message.content

    if not content:
        raise RuntimeError("Groq returned an empty response.")

    result = json.loads(content)

    # Validate the main response.
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

    entities = result["entities"]

    # Validate multi-product structure.
    items = entities.get("items")

    if not isinstance(items, list):
        raise ValueError("Entities.items must be a list.")

    for item in items:

        if not isinstance(item, dict):
            raise ValueError("Invalid product item.")

        if not all(
            key in item
            for key in ("product", "quantity", "unit")
        ):
            raise ValueError("Product item is missing required fields.")

        product = item["product"]
        quantity = item["quantity"]
        unit = item["unit"]

        if not isinstance(product, (str, type(None))):
            raise ValueError("Invalid product name.")

        if not isinstance(unit, (str, type(None))):
            raise ValueError("Invalid product unit.")

        if isinstance(quantity, bool):
            raise ValueError("Invalid product quantity.")

        if not isinstance(
            quantity,
            (int, float, str, type(None))
        ):
            raise ValueError("Invalid product quantity.")

    # Validate remaining entities.
    for key in ("customer", "payment_method"):
        if not isinstance(
            entities.get(key),
            (str, type(None))
        ):
            raise ValueError(f"Invalid {key}.")

    amount = entities.get("amount")

    if isinstance(amount, bool) or not isinstance(
        amount, (int, float, str, type(None))
    ):
        raise ValueError("Invalid amount.")

    return result
