import json

from services.llm_service import get_groq_client, MODEL

client = get_groq_client()

def resolve_product_with_llm(spoken_name, products):
    """
    Match a spoken product name against the shop's catalogue.

    Returns a database product only when Groq selects a valid
    product ID from the supplied catalogue.
    """

    if not spoken_name or not products:
        return None

    catalogue = []

    for product in products:
        aliases = [
            alias.alias
            for alias in getattr(product, "aliases", [])
        ]

        catalogue.append({
            "id": product.id,
            "name": product.name,
            "aliases": aliases
        })

    system_prompt = """
You are a product-matching assistant for an Indian shop.

Match the spoken product name against the supplied catalogue.

Understand Hindi, Devanagari Hindi, Hinglish and English.

Rules:
1. Select only a product that exists in the catalogue.
2. Consider translations, transliterations and common spoken variations.
3. Prefer the most specific matching product.
4. Do not match a generic product to a specific variant without
   sufficient evidence.
5. If multiple products are plausible, return ambiguous.
6. Never invent a product or product ID.
7. Do not use quantity, price or stock to guess the product.

Return JSON only:

{
    "status": "matched",
    "product_id": 1,
    "confidence": "high"
}

For an ambiguous or unmatched product:

{
    "status": "ambiguous",
    "product_id": null,
    "confidence": "low"
}
"""

    user_prompt = f"""
SHOP CATALOGUE:
{json.dumps(catalogue, ensure_ascii=False)}

SPOKEN PRODUCT:
{spoken_name}
"""

    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_completion_tokens=150
        )

        content = completion.choices[0].message.content

        if not content:
            return None

        result = json.loads(content)

        if (
                result.get("status") != "matched"
                or result.get("confidence") != "high"
        ):
            return None

        product_id = result.get("product_id")

        if isinstance(product_id, bool) or not isinstance(product_id, int):
            return None

        # Always validate against the actual supplied catalogue.
        return next(
            (p for p in products if p.id == product_id),
            None
        )

    except Exception:
        # Preserve local matching if Groq is unavailable.
        return None
