
from decimal import Decimal, InvalidOperation

from database.db import db
from database.models import Product


ALLOWED_UNITS = {
    "kg", "g", "litre", "ml", "piece",
    "packet", "box", "dozen", "bottle", "bag"
}


def _to_decimal(value, field_name):
    """Convert a value into a finite Decimal."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field_name} ki value valid nahi hai.")

    if not number.is_finite():
        raise ValueError(f"{field_name} ki value valid nahi hai.")

    return number


def create_product(
    user,
    name,
    cost_price,
    selling_price,
    unit,
    stock_quantity,
    low_stock_threshold=None
):
    """
    Create a product for the owner's shop.

    Only owners can create products through this service.
    """

    # 1. Permission validation
    if not user or user.role != "owner":
        raise PermissionError(
            "Sirf shop owner naye products add kar sakta hai."
        )

    if not user.shop_id:
        raise ValueError("User kisi shop se associated nahi hai.")

    # 2. Basic validation
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Product ka naam zaroori hai.")

    name = name.strip()

    if len(name) > 100:
        raise ValueError("Product ka naam 100 characters se chhota rakhein.")

    if not isinstance(unit, str):
        raise ValueError("Product ki unit valid nahi hai.")

    unit = unit.strip().lower()

    if unit not in ALLOWED_UNITS:
        raise ValueError(
            "Unit valid nahi hai. Available units: "
            + ", ".join(sorted(ALLOWED_UNITS))
        )

    # 3. Price validation
    cost_price = _to_decimal(cost_price, "Buying price")
    selling_price = _to_decimal(selling_price, "Selling price")

    if cost_price < 0:
        raise ValueError("Buying price negative nahi ho sakta.")

    if selling_price <= 0:
        raise ValueError("Selling price zero se zyada hona chahiye.")

    cost_price = cost_price.quantize(Decimal("0.01"))
    selling_price = selling_price.quantize(Decimal("0.01"))

    # 4. Stock validation
    stock_quantity = _to_decimal(stock_quantity, "Stock")

    if stock_quantity < 0:
        raise ValueError("Stock negative nahi ho sakta.")

    stock_quantity = stock_quantity.quantize(Decimal("0.001"))

    # 5. Optional low-stock threshold
    if low_stock_threshold is not None:
        low_stock_threshold = _to_decimal(
            low_stock_threshold,
            "Low stock threshold"
        )

        if low_stock_threshold < 0:
            raise ValueError("Low stock threshold negative nahi ho sakta.")

        low_stock_threshold = low_stock_threshold.quantize(
            Decimal("0.001")
        )

    # 6. Prevent duplicate product names in the same shop
    existing_product = Product.query.filter(
        Product.shop_id == user.shop_id,
        db.func.lower(Product.name) == name.lower()
    ).first()

    if existing_product:
        raise ValueError(
            f"{name} pehle se inventory mein available hai."
        )

    # 7. Create product
    product = Product(
        name=name,
        cost_price=cost_price,
        price=selling_price,
        unit=unit,
        stock_quantity=stock_quantity,
        low_stock_threshold=low_stock_threshold,
        shop_id=user.shop_id
    )

    try:
        db.session.add(product)
        db.session.commit()

        return product

    except Exception:
        db.session.rollback()
        raise
