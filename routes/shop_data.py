
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation

from database.db import db
from database.models import Product, Customer

shop_data = Blueprint("shop_data", __name__)


@shop_data.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        try:
            price = Decimal(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))

            if not price.is_finite() or price < 0 or stock < 0:
                raise ValueError

        except (InvalidOperation, ValueError, TypeError):
            flash("Enter a valid price and stock quantity.")
            return redirect(url_for("shop_data.inventory"))

        if not name:
            flash("Product name is required.")
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
            price=price,
            stock_quantity=stock,
            shop_id=current_user.shop_id
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully!")
        return redirect(url_for("shop_data.inventory"))

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Product.name).all()

    return render_template("inventory.html", products=products)


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
