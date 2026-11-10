import json

from services.llm_service import get_groq_client, MODEL
from services.entity_extractor import normalize


ALLOWED_ACTIONS = {
    "cancel",
    "approve",
    "reject",
    "provide_information",
    "unclear"
}


def interpret_conversation_reply(reply, pending):
    """
    Interpret a reply using the current conversation context.

    This function only interprets language.
    It never modifies the database or executes a transaction.
    """

    if not isinstance(reply, str) or not reply.strip():
        return {"action": "unclear", "confidence": "low"}

    context = {
        "action": pending.get("action"),
        "awaiting": pending.get("awaiting"),
        "customer_name": pending.get("customer_name"),
        "items": pending.get("items", []),
        "payment_method": pending.get("payment_method"),
        "question": pending.get("last_question")
    }

    system_prompt = f"""
You are Chotu, a conversational interpreter for an Indian shopkeeper.

Understand Hindi, Devanagari Hindi, Hinglish and English.

CURRENT CONVERSATION:
{json.dumps(context, ensure_ascii=False, default=str)}

LATEST SHOPKEEPER REPLY:
{reply}

Classify the reply into exactly one action:

1. cancel:
   The shopkeeper wants to stop or cancel the current pending task.
   Examples: "order cancel kar de", "ab rehne do",
   "okay cancel it", "ऑर्डर कैंसिल कर दो".

2. approve:
   The shopkeeper agrees to the specific pending permission question.
   Use this only when awaiting is customer_creation.

3. reject:
   The shopkeeper refuses the specific pending permission question.
   Use this only when awaiting is customer_creation.

4. provide_information:
   The shopkeeper is answering the pending question or providing
   information relevant to the current task.

5. unclear:
   The meaning is uncertain or unrelated.

IMPORTANT:
- Interpret meaning, not exact words.
- Ignore punctuation differences.
- Do not treat every "haan" as approval unless customer_creation
  permission is currently being requested.
- Do not treat every "nahi" as cancellation.
- Do not invent product names, quantities, customers or payment details.
- Never claim that a transaction has been completed.
- A new sale command is not a reply; classify it as unclear here.
  The main NLU handles new sale commands separately.

Return only JSON:
{{
    "action": "unclear",
    "confidence": "low"
}}
"""
    client = get_groq_client()
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": reply}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_completion_tokens=150
    )

    content = completion.choices[0].message.content

    if not content:
        return {"action": "unclear", "confidence": "low"}

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        return {"action": "unclear", "confidence": "low"}

    action = result.get("action")
    confidence = result.get("confidence")

    if action not in ALLOWED_ACTIONS:
        return {"action": "unclear", "confidence": "low"}

    if confidence not in {"high", "medium", "low"}:
        return {"action": "unclear", "confidence": "low"}

    return result