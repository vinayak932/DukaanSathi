
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_PLACES = Decimal("0.01")
QUANTITY_PLACES = Decimal("0.001")


def to_decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Please provide a valid number.")

    if not number.is_finite():
        raise ValueError("Invalid number.")

    return number


def round_money(value):
    return value.quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP
    )


def round_quantity(value):
    return value.quantize(
        QUANTITY_PLACES,
        rounding=ROUND_HALF_UP
    )


def calculate_product_line(
    product,
    quantity=None,
    amount=None,
    pack=None,
    pack_count=1
):

    selected_modes = sum([
        quantity is not None,
        amount is not None,
        pack is not None
    ])

    if selected_modes != 1:
        raise ValueError(
            "Provide either quantity, amount, or a pack."
        )

    product_price = to_decimal(product.price)

    # Quantity-based calculation
    if quantity is not None:
        quantity = to_decimal(quantity)

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        total = round_money(quantity * product_price)

        return {
            "product": product.name,
            "quantity": quantity,
            "unit": product.unit,
            "unit_price": product_price,
            "total": total,
            "description": f"{quantity} {product.unit}"
        }

    # Amount-based calculation
    if amount is not None:
        amount = to_decimal(amount)

        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        if product_price <= 0:
            raise ValueError(
                "This product does not have a usable selling price."
            )

        quantity = round_quantity(amount / product_price)

        return {
            "product": product.name,
            "quantity": quantity,
            "unit": product.unit,
            "unit_price": product_price,
            "total": round_money(amount),
            "description": f"₹{amount} worth"
        }

    # Pack-based calculation
    pack_count = to_decimal(pack_count)

    if pack_count <= 0:
        raise ValueError("Pack count must be greater than zero.")

    pack_quantity = to_decimal(pack.quantity)
    pack_price = to_decimal(pack.price)

    if pack_quantity <= 0 or pack_price < 0:
        raise ValueError("Invalid pack details.")

    actual_quantity = round_quantity(
        pack_quantity * pack_count
    )

    total = round_money(pack_price * pack_count)

    return {
        "product": product.name,
        "quantity": actual_quantity,
        "unit": product.unit,
        "unit_price": round_money(pack_price / pack_quantity),
        "total": total,
        "pack_name": pack.pack_name,
        "pack_count": pack_count,
        "description": f"{pack_count} x {pack.pack_name}"
    }


def calculate_total(lines):
    if not lines:
        raise ValueError("No products to calculate.")

    total = sum(
        (to_decimal(line["total"]) for line in lines),
        Decimal("0.00")
    )

    return round_money(total)
