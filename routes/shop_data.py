from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database.db import db
from database.models import Product, ProductPack, Customer, Sale, SaleItem

shop_data = Blueprint("shop_data", __name__)

ALLOWED_UNITS = [
    "kg", "g", "litre", "ml", "piece",
    "packet", "box", "dozen", "bottle", "bag"
]


def get_decimal(value):
    number = Decimal(value)

    if not number.is_finite():
        raise ValueError("Invalid number")

    return number


# ---------------- INVENTORY ----------------

@shop_data.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():
    if request.method == "POST":

        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip().lower()

        try:
            cost_price = get_decimal(request.form.get("cost_price", ""))
            price = get_decimal(request.form.get("price", ""))
            stock = get_decimal(request.form.get("stock", ""))

            threshold_input = request.form.get("low_stock_threshold", "").strip()
            threshold = (
                get_decimal(threshold_input)
                if threshold_input else None
            )

            if (
                    cost_price < 0 or price < 0 or stock < 0
                    or (threshold is not None and threshold < 0)
            ):
                raise ValueError("Negative values are not allowed")

        except (InvalidOperation, ValueError, TypeError):
            flash("Please enter valid prices and quantities.")
            return redirect(url_for("shop_data.inventory"))

        if not name:
            flash("Product name is required.")
            return redirect(url_for("shop_data.inventory"))

        if unit not in ALLOWED_UNITS:
            flash("Please select a valid unit.")
            return redirect(url_for("shop_data.inventory"))

        existing = Product.query.filter(
            Product.shop_id == current_user.shop_id,
            db.func.lower(Product.name) == name.lower()
        ).first()

        if existing:
            flash("This product already exists.")
            return redirect(url_for("shop_data.inventory"))

        product = Product(
            name=name,
            cost_price=cost_price,
            price=price,
            unit=unit,
            stock_quantity=stock,
            low_stock_threshold=threshold,
            shop_id=current_user.shop_id
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully!")
        return redirect(url_for("shop_data.inventory"))

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Product.name).all()

    return render_template(
        "inventory.html",
        products=products,
        units=ALLOWED_UNITS
    )


# ---------------- PRODUCT PACKS ----------------

@shop_data.route(
    "/inventory/<int:product_id>/packs",
    methods=["POST"]
)
@login_required
def add_product_pack(product_id):
    product = Product.query.filter_by(
        id=product_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    pack_name = request.form.get("pack_name", "").strip()

    try:
        quantity = get_decimal(request.form.get("quantity", ""))
        pack_price = get_decimal(request.form.get("price", ""))

        if quantity <= 0 or pack_price < 0:
            raise ValueError("Invalid pack values")

    except (InvalidOperation, ValueError, TypeError):
        flash("Please enter a valid pack quantity and price.")
        return redirect(url_for("shop_data.inventory"))

    if not pack_name:
        flash("Pack name is required.")
        return redirect(url_for("shop_data.inventory"))

    pack = ProductPack(
        product_id=product.id,
        pack_name=pack_name,
        quantity=quantity,
        price=pack_price
    )

    db.session.add(pack)
    db.session.commit()

    flash(f"{pack_name} added successfully!")
    return redirect(url_for("shop_data.inventory"))


# ---------------- CUSTOMERS ----------------

@shop_data.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name:
            flash("Customer name is required.")
            return redirect(url_for("shop_data.customers"))

        customer = Customer(
            name=name,
            phone=phone or None,
            shop_id=current_user.shop_id
        )

        db.session.add(customer)
        db.session.commit()

        flash("Customer added successfully!")
        return redirect(url_for("shop_data.customers"))

    customer_list = Customer.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Customer.name).all()

    return render_template(
        "customers.html",
        customers=customer_list
    )


# ---------------- SALES ----------------

@shop_data.route("/sales/record", methods=["POST"])
@login_required
def record_sale():

    try:
        product_id = int(request.form.get("product_id", ""))

        product = Product.query.filter_by(
            id=product_id,
            shop_id=current_user.shop_id
        ).first()

        if not product:
            raise ValueError("Product not found.")

        payment_method = request.form.get(
            "payment_method", ""
        ).strip().lower()

        if payment_method not in ["cash", "upi", "udhaar"]:
            raise ValueError("Invalid payment method.")

        # Customer is optional.
        customer_input = request.form.get("customer_id", "").strip()
        customer = None

        if customer_input == "new":

            customer_name = request.form.get(
                "new_customer_name", ""
            ).strip()

            customer_phone = request.form.get(
                "new_customer_phone", ""
            ).strip()

            if not customer_name:
                raise ValueError("Please enter the customer's name.")

            customer = Customer(
                name=customer_name,
                phone=customer_phone or None,
                shop_id=current_user.shop_id
            )

            db.session.add(customer)
            db.session.flush()

        elif customer_input:

            try:
                customer_id = int(customer_input)
            except ValueError:
                raise ValueError("Invalid customer selection.")

            customer = Customer.query.filter_by(
                id=customer_id,
                shop_id=current_user.shop_id
            ).first()

            if not customer:
                raise ValueError("Customer not found.")

        quantity_input = request.form.get("quantity", "").strip()
        amount_input = request.form.get("amount", "").strip()
        pack_input = request.form.get("pack_id", "").strip()

        pack_name = None

        # -------- PACK SALE --------

        if pack_input:

            if amount_input:
                raise ValueError(
                    "For pack sales, use the pack's listed price."
                )

            pack = ProductPack.query.filter_by(
                id=int(pack_input),
                product_id=product.id,
                is_active=True
            ).first()

            if not pack:
                raise ValueError("Invalid pack selected.")

            pack_count = get_decimal(quantity_input)

            if pack_count <= 0:
                raise ValueError("Pack quantity must be positive.")

            actual_quantity = pack.quantity * pack_count
            total_amount = pack.price * pack_count
            pack_name = pack.pack_name

        # -------- LOOSE PRODUCT SALE --------

        else:

            if not quantity_input and not amount_input:
                raise ValueError(
                    "Enter either the quantity or the amount."
                )

            if quantity_input:
                actual_quantity = get_decimal(quantity_input)

                if actual_quantity <= 0:
                    raise ValueError("Quantity must be positive.")

            else:
                amount = get_decimal(amount_input)

                if amount <= 0 or product.price <= 0:
                    raise ValueError("Cannot calculate quantity.")

                actual_quantity = (
                    amount / product.price
                ).quantize(
                    Decimal("0.001"),
                    rounding=ROUND_HALF_UP
                )

            if actual_quantity <= 0:
                raise ValueError("Invalid calculated quantity.")

            if amount_input:
                # Preserve the actual amount agreed with the customer.
                total_amount = get_decimal(amount_input)

                if total_amount <= 0:
                    raise ValueError("Amount must be positive.")

            else:
                total_amount = actual_quantity * product.price

        total_amount = total_amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        # -------- STOCK VALIDATION --------

        if actual_quantity > product.stock_quantity:
            raise ValueError(
                f"Only {product.stock_quantity} {product.unit} "
                "is available."
            )

        # -------- PAYMENT --------

        if payment_method in ["cash", "upi"]:
            paid_amount = total_amount
        else:
            paid_amount = Decimal("0.00")

        # -------- SAVE SALE --------

        sale = Sale(
            shop_id=current_user.shop_id,
            customer_id=customer.id if customer else None,
            total_amount=total_amount,
            paid_amount=paid_amount,
            payment_method=payment_method
        )

        db.session.add(sale)
        db.session.flush()

        effective_unit_price = (
            total_amount / actual_quantity
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            product_name=product.name,
            quantity=actual_quantity,
            unit=product.unit,
            unit_price=effective_unit_price,
            line_total=total_amount,
            pack_name=pack_name
        )

        db.session.add(sale_item)

        # Deduct stock.
        product.stock_quantity -= actual_quantity

        # Update customer khata for udhaar.
        if payment_method == "udhaar" and customer:
            current_balance = (
                customer.outstanding_balance or Decimal("0.00")
            )
            customer.outstanding_balance = (
                current_balance + total_amount
            )

        db.session.commit()

        flash(
            f"Sale recorded successfully! Total: ₹{total_amount}"
        )

    except (ValueError, InvalidOperation, TypeError, OverflowError) as error:
        db.session.rollback()
        flash(str(error))

    except Exception:
        db.session.rollback()
        flash("Something went wrong. The sale was not recorded.")

    return redirect(url_for("shop_data.sales"))

# ---------------- SALES PAGE ----------------

@shop_data.route("/sales", methods=["GET"])
@login_required
def sales():

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Product.name).all()

    customers = Customer.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Customer.name).all()

    packs = ProductPack.query.join(Product).filter(
        Product.shop_id == current_user.shop_id,
        ProductPack.is_active == True
    ).all()

    return render_template(
        "sales.html",
        products=products,
        customers=customers,
        packs=packs
    )


