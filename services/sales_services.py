from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from database.db import db
from database.models import Product, Customer, Sale, SaleItem, CustomerPayment
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import func

MONEY_PLACES = Decimal("0.01")


def record_confirmed_sale(user_id, shop_id, pending):
    """
    Record a completed sale containing one or multiple products.

    No final confirmation flag is required.
    All items are validated before any database changes are committed.
    """

    if not isinstance(pending, dict):
        raise ValueError("Invalid transaction details.")

    raw_items = pending.get("items")

    # Backward compatibility with the previous single-product structure.
    if not raw_items and pending.get("product_id"):
        raw_items = [{
            "product_id": pending["product_id"],
            "quantity": pending.get("quantity"),
            "unit": pending.get("unit")
        }]

    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Sale mein koi product nahi hai.")

    payment_method = str(
        pending.get("payment_method") or ""
    ).strip().lower()

    if payment_method not in ["cash", "upi", "udhaar"]:
        raise ValueError("Payment method valid nahi hai.")

    try:
        # Resolve and validate customer.
        customer = None
        customer_id = pending.get("customer_id")

        if customer_id is not None:
            customer = Customer.query.filter_by(
                id=int(customer_id),
                shop_id=shop_id
            ).first()

            if customer is None:
                raise ValueError("Customer not found.")

        if payment_method == "udhaar" and customer is None:
            raise ValueError(
                "Udhaar record karne ke liye customer zaroori hai."
            )

        # Validate all items before changing stock.
        validated_items = []
        required_stock = {}
        total_amount = Decimal("0.00")

        for item in raw_items:
            product_id = int(item["product_id"])
            quantity = Decimal(str(item["quantity"]))

            if not quantity.is_finite() or quantity <= 0:
                raise ValueError("Invalid sale quantity.")

            product = Product.query.filter_by(
                id=product_id,
                shop_id=shop_id
            ).with_for_update().first()

            if product is None:
                raise ValueError("Product not found.")

            unit = str(item.get("unit") or "").strip().lower()

            if unit != product.unit.lower():
                raise ValueError(
                    f"{product.name} ka unit {product.unit} hona chahiye."
                )

            unit_price = Decimal(str(product.price))

            line_total = (
                    quantity * unit_price
            ).quantize(
                MONEY_PLACES,
                rounding=ROUND_HALF_UP
            )

            validated_items.append({
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total
            })

            required_stock[product.id] = (
                    required_stock.get(product.id, Decimal("0"))
                    + quantity
            )

            total_amount += line_total

        # Check combined quantities to prevent overselling
        # when the same product appears more than once.
        for product_id, quantity in required_stock.items():
            product = next(
                item["product"]
                for item in validated_items
                if item["product"].id == product_id
            )

            if quantity > Decimal(str(product.stock_quantity)):
                raise ValueError(
                    f"{product.name} ka stock sirf "
                    f"{product.stock_quantity} {product.unit} hai."
                )

        total_amount = total_amount.quantize(
            MONEY_PLACES,
            rounding=ROUND_HALF_UP
        )

        paid_amount = (
            total_amount
            if payment_method in ["cash", "upi"]
            else Decimal("0.00")
        )

        # Create one sale header.
        sale = Sale(
            shop_id=shop_id,
            customer_id=customer.id if customer else None,
            total_amount=total_amount,
            paid_amount=paid_amount,
            payment_method=payment_method
        )

        db.session.add(sale)
        db.session.flush()

        # Create multiple sale items.
        for item in validated_items:
            product = item["product"]
            quantity = item["quantity"]

            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                product_name=product.name,
                quantity=quantity,
                unit=product.unit,
                unit_price=item["unit_price"],
                line_total=item["line_total"],
                pack_name=None
            )

            db.session.add(sale_item)

        # Deduct stock once per product.
        for product_id, quantity in required_stock.items():
            product = next(
                item["product"]
                for item in validated_items
                if item["product"].id == product_id
            )

            product.stock_quantity -= quantity

        # Update customer balance for credit sales.
        if payment_method == "udhaar":
            balance = Decimal(
                str(customer.outstanding_balance or "0")
            )
            customer.outstanding_balance = balance + total_amount

        # Commit everything together.
        db.session.commit()

        return sale

    except (ValueError, InvalidOperation, TypeError, KeyError):
        db.session.rollback()
        raise

    except Exception:
        db.session.rollback()
        raise


def record_customer_payment(shop_id, customer_id, amount, payment_method="cash"):
    try:
        amount = Decimal(str(amount)).quantize(
            MONEY_PLACES,
            rounding=ROUND_HALF_UP
        )

        payment_method = str(payment_method).strip().lower()

        if not amount.is_finite() or amount <= 0:
            raise ValueError("Valid repayment amount batayein.")

        if payment_method not in ["cash", "upi"]:
            raise ValueError(
                "Repayment method cash ya UPI hona chahiye."
            )

        customer = Customer.query.filter_by(
            id=customer_id,
            shop_id=shop_id
        ).with_for_update().first()

        if not customer:
            raise ValueError("Customer nahi mila.")

        balance = Decimal(
            str(customer.outstanding_balance or "0")
        )

        if balance <= 0:
            raise ValueError(
                "Is customer ka koi outstanding udhaar nahi hai."
            )

        if amount > balance:
            raise ValueError(
                f"Customer ka total udhaar ₹{balance} hai."
            )

        # Update outstanding balance.
        customer.outstanding_balance = (
                balance - amount
        ).quantize(MONEY_PLACES)

        # Save repayment history.
        payment = CustomerPayment(
            customer_id=customer.id,
            shop_id=shop_id,
            amount=amount,
            payment_method=payment_method
        )

        db.session.add(payment)

        # Both changes succeed or fail together.
        db.session.commit()

        return customer

    except (ValueError, InvalidOperation, TypeError):
        db.session.rollback()
        raise

    except Exception:
        db.session.rollback()
        raise

def get_today_sales_summary(shop_id, payment_method=None):
    india_tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(india_tz).date()

    start_local = datetime.combine(
        today,
        time.min,
        tzinfo=india_tz
    )

    end_local = datetime.combine(
        today,
        time.max,
        tzinfo=india_tz
    )

    start_utc = start_local.astimezone(
        timezone.utc
    ).replace(tzinfo=None)

    end_utc = end_local.astimezone(
        timezone.utc
    ).replace(tzinfo=None)

    query = db.session.query(
        func.coalesce(func.sum(Sale.total_amount), 0)
    ).filter(
        Sale.shop_id == shop_id,
        Sale.created_at >= start_utc,
        Sale.created_at <= end_utc
    )

    if payment_method in ["cash", "upi", "udhaar"]:
        query = query.filter(
            Sale.payment_method == payment_method
        )

    result = query.scalar()

    return {
        "date": today.isoformat(),
        "payment_method": payment_method or "total",
        "total_sales": float(result)
    }
