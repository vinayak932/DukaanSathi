import os
import tempfile
import base64
from pathlib import Path
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from flask import current_app as app
from services.intent_parser import detect_inventory_query_type
from services.intent_parser import detect_sales_query_type
from services.sales_services import get_today_sales_summary
from services.gnani_service import transcribe_audio, synthesize_speech
from services.nlu_service import understand_user_message
from services.entity_resolver import resolve_llm_entities
from services.conversation_store import get_active_conversation
import re

from services.conversation_manager import (
    begin_sale,
    begin_product_clarification,
    handle_conversation_reply,
    begin_payment_conversation,
    handle_payment_reply
)

from database.models import Product, Customer

voice = Blueprint("voice", __name__)

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".webm",
    ".flac",
    ".aac"
}

PRODUCT_ALIASES = {
    "राइस": "rice",
    "चावल": "rice",
    "शुगर": "sugar",
    "चीनी": "sugar",
    "दूध": "milk",
    "मिल्क": "milk",
}

CUSTOMER_ALIASES = {
    "रमेश": "ramesh",
    "सुरेश": "suresh",
    "महेश": "mahesh",
    "राजेश": "rajesh",
}


def normalize_product_aliases(text):
    text = normalize_product_text(text)

    for hindi, english in PRODUCT_ALIASES.items():
        text = text.replace(hindi, english)

    return text


def normalize_product_text(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", text)
    return " ".join(text.split())


def generate_response_audio(response_text):
    """Generate optional WAV audio without affecting business operations."""
    if not response_text:
        return None

    try:
        audio_bytes = synthesize_speech(response_text)
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception:
        app.logger.exception("Timbre TTS failed")
        return None


@voice.route("/voice/transcribe", methods=["POST"])
@login_required
def transcribe():
    audio = request.files.get("audio")

    if not audio or not audio.filename:
        return jsonify({
            "success": False,
            "error": "No audio file received."
        }), 400

    extension = Path(audio.filename).suffix.lower()

    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported audio file format."
        }), 400

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
                suffix=extension,
                delete=False
        ) as temp_file:

            temp_path = temp_file.name
            audio.save(temp_path)

        # Limit uploaded audio to 16 MB.
        if os.path.getsize(temp_path) > 16 * 1024 * 1024:
            return jsonify({
                "success": False,
                "error": "Audio file is too large. Maximum size is 16 MB."
            }), 413

        # 1. Speech to text.
        stt_result = transcribe_audio(
            temp_path,
            language_code="hi-IN"
        )

        transcript = stt_result.get("transcript", "").strip()

        if not transcript:
            return jsonify({
                "success": False,
                "error": "Speech could not be recognised."
            }), 422

        user_id = current_user.id
        shop_id = current_user.shop_id

        if not shop_id:
            return jsonify({
                "success": False,
                "error": "Your account is not linked to a shop."
            }), 400

        # 2. Load this shop's products and customers.
        products = Product.query.filter_by(
            shop_id=shop_id
        ).all()

        customers = Customer.query.filter_by(
            shop_id=shop_id
        ).all()

        # 3. Retrieve any active conversation.
        active_conversation = get_active_conversation(
            user_id,
            shop_id
        )

        # 4. Run NLU to identify new tasks versus replies.
        nlu_result = understand_user_message(transcript)

        intent = nlu_result.get("intent")

        conversation_result = None

        # --------------------------------------------------
        # 5. Handle existing conversations FIRST.
        # --------------------------------------------------

        # 5A. Existing repayment conversation.
        if (
                active_conversation is not None
                and active_conversation.get("type") == "customer_payment"
        ):

            # Do not allow another transaction to overwrite repayment.
            if intent in ("record_sale", "record_payment"):

                conversation_result = {
                    "status": "PENDING_TRANSACTION_EXISTS",
                    "response": (
                        "Ek repayment abhi pending hai. "
                        "Pehle usse complete ya cancel kar dijiye."
                    )
                }

            else:
                conversation_result = handle_payment_reply(
                    user_id=user_id,
                    shop_id=shop_id,
                    reply=transcript,
                    customers=customers
                )

                nlu_result = {
                    "intent": "conversation_reply",
                    "confidence": "not_applicable"
                }

        # 5B. A repayment cannot overwrite an active sale.
        elif (
                active_conversation is not None
                and active_conversation.get("type") != "customer_payment"
                and intent == "record_payment"
        ):

            conversation_result = {
                "status": "PENDING_TRANSACTION_EXISTS",
                "response": (
                    "Ek sale abhi pending hai. "
                    "Pehle usse complete ya cancel kar dijiye."
                )
            }

        # 5C. Handle every other existing conversation.
        # This includes sale clarification and product creation.
        elif active_conversation is not None:

            conversation_result = handle_conversation_reply(
                user_id=user_id,
                shop_id=shop_id,
                reply=transcript,
                products=products,
                customers=customers
            )

            nlu_result = {
                "intent": "conversation_reply",
                "confidence": "not_applicable"
            }

        # --------------------------------------------------
        # 6. Start a new repayment conversation.
        # --------------------------------------------------

        elif intent == "record_payment":

            entities = nlu_result.get("entities") or {}

            conversation_result = begin_payment_conversation(
                user_id=user_id,
                shop_id=shop_id,
                transcript=transcript,
                entities=entities,
                customers=customers
            )

        # --------------------------------------------------
        # 7. Start a new sale.
        # --------------------------------------------------

        elif intent == "record_sale":

            entities = resolve_llm_entities(
                nlu_result,
                products,
                customers
            )

            if entities.get("product_status") == "AMBIGUOUS":

                conversation_result = begin_product_clarification(
                    user_id=user_id,
                    shop_id=shop_id,
                    entities=entities
                )

            else:

                conversation_result = begin_sale(
                    user_id=user_id,
                    shop_id=shop_id,
                    entities=entities,
                    products=products,
                    customers=customers
                )

        # --------------------------------------------------
        # 8. Handle inventory queries.
        # --------------------------------------------------

        elif intent == "query_records" and any(
                word in transcript.lower()
                for word in [
                    "stock", "inventory", "बचा",
                    "बची", "बचे", "खत्म", "कम स्टॉक"
                ]
        ):

            query_type = detect_inventory_query_type(transcript)

            # A. Out-of-stock products
            if query_type == "out_of_stock":

                matching_products = [
                    p for p in products
                    if float(p.stock_quantity) <= 0
                ]

                if matching_products:
                    names = ", ".join(
                        p.name for p in matching_products
                    )

                    response = f"इन products का stock खत्म हो गया है: {names}।"
                else:
                    response = "आपकी दुकान में कोई product out of stock नहीं है।"

            # B. Low-stock products
            elif query_type == "low_stock":

                matching_products = [
                    p for p in products
                    if (
                            p.low_stock_threshold is not None
                            and p.stock_quantity <= p.low_stock_threshold
                            and p.stock_quantity > 0
                    )
                ]

                if matching_products:
                    details = ", ".join(
                        f"{p.name}: {p.stock_quantity} {p.unit}"
                        for p in matching_products
                    )

                    response = f"कम stock वाले products हैं: {details}।"
                else:
                    response = (
                        "Configured low-stock thresholds के अनुसार "
                        "अभी कोई product कम stock में नहीं है।"
                    )

            # C. Specific product stock
            else:

                spoken_text = normalize_product_aliases(transcript)

                matching_products = [
                    p for p in products
                    if normalize_product_aliases(p.name) in spoken_text
                ]

                if len(matching_products) == 1:

                    product = matching_products[0]

                    response = (
                        f"{product.name} का stock "
                        f"{product.stock_quantity} {product.unit} बचा है।"
                    )

                elif len(matching_products) > 1:

                    names = ", ".join(
                        p.name for p in matching_products
                    )

                    response = (
                        f"कृपया इनमें से एक product स्पष्ट करें: {names}।"
                    )

                else:
                    response = (
                        "यह product आपकी inventory में नहीं मिला। "
                        "कृपया उसका नाम दोबारा बताएं।"
                    )

            conversation_result = {
                "status": "QUERY_COMPLETED",
                "response": response
            }

        # --------------------------------------------------
        # 9. Handle sales queries.
        # --------------------------------------------------

        elif intent == "query_records" and (
                "बिक्री" in transcript
                or "सेल" in transcript
                or "sales" in transcript.lower()
                or "sale" in transcript.lower()
        ):

            query_type = detect_sales_query_type(transcript)

            summary = get_today_sales_summary(
                shop_id,
                payment_method=(
                    query_type if query_type != "total" else None
                )
            )

            labels = {
                "cash": "नकद बिक्री",
                "upi": "UPI बिक्री",
                "udhaar": "उधार बिक्री",
                "total": "कुल बिक्री"
            }

            conversation_result = {
                "status": "QUERY_COMPLETED",
                "response": (
                    f"आज की {labels[query_type]} "
                    f"{summary['total_sales']:.2f} रुपये हुई है।"
                )
            }


        # --------------------------------------------------
        # 10. Handle customer udhaar queries.
        # --------------------------------------------------

        elif intent == "query_records" and any(
                word in transcript.lower()
                for word in [
                    "udhaar", "उधार", "उधारी",
                    "बाकी", "balance", "खाता",
                    "customer", "ग्राहक"
                ]
        ):

            normalized_transcript = normalize_product_text(transcript)

            # A. Find a specific customer.
            matching_customers = [
                c for c in customers
                if normalize_product_text(c.name) in normalized_transcript
            ]

            if len(matching_customers) == 1:

                customer = matching_customers[0]
                balance = float(customer.outstanding_balance or 0)

                response = (
                    f"{customer.name} का कुल बकाया उधार "
                    f"{balance:.2f} रुपये है।"
                )

            elif len(matching_customers) > 1:

                names = ", ".join(
                    c.name for c in matching_customers
                )

                response = (
                    f"कृपया customer का नाम स्पष्ट करें: {names}।"
                )

            else:

                # B. Aggregate queries.
                pending_customers = [
                    c for c in customers
                    if float(c.outstanding_balance or 0) > 0
                ]

                total_outstanding = sum(
                    float(c.outstanding_balance or 0)
                    for c in pending_customers
                )

                if any(word in normalized_transcript for word in [
                    "kitne customer", "kitne grahak",
                    "कितने ग्राहक", "कितने कस्टमर"
                ]):

                    response = (
                        f"आपके {len(pending_customers)} customers का "
                        f"उधार अभी बाकी है।"
                    )

                else:

                    response = (
                        f"आपकी दुकान का कुल बकाया उधार "
                        f"{total_outstanding:.2f} रुपये है।"
                    )

            conversation_result = {
                "status": "QUERY_COMPLETED",
                "response": response
            }


        # --------------------------------------------------
        # 11. No active conversation or supported task.
        # --------------------------------------------------

        else:
            response_text = nlu_result.get("response")
            audio_base64 = generate_response_audio(response_text)

            return jsonify({
                "success": True,
                "intent": nlu_result,
                "response": response_text,
                "audio": audio_base64
            }), 200

        # --------------------------------------------------
        # 12. Return Chotu's response.
        # --------------------------------------------------

        response_text = conversation_result.get("response")
        audio_base64 = generate_response_audio(response_text)

        return jsonify({
            "success": True,
            "intent": nlu_result,
            "conversation": {
                "status": conversation_result.get("status"),
                "response": response_text,
                "sale_id": conversation_result.get("sale_id"),
                "total_amount": conversation_result.get("total_amount")
            },
            "response": response_text,
            "audio": audio_base64,
            "end_to_end_latency": stt_result.get(
                "end_to_end_latency"
            ),
            "processing_time": stt_result.get(
                "processing_time"
            ),
            "model": stt_result.get("model")
        }), 200

    except Exception as error:
        print("VOICE PROCESSING ERROR:", repr(error))
        app.logger.exception("Voice processing failed")

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)