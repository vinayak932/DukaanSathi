from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import db
from database.models import Shop, User

auth = Blueprint("auth", __name__)

@auth.route("/register", methods=["GET", "POST"])
def register():

    # Always display registration page on GET
    if request.method == "GET":
        return render_template("register.html")

    # Check for existing shop only after form submission
    if Shop.query.first():
        flash("A shop is already registered. Please log in.")
        return redirect(url_for("auth.login"))

    shop_name = request.form.get("shop_name", "").strip()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not all([shop_name, username, email, password]):
        flash("All fields are required.")
        return redirect(url_for("auth.register"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.")
        return redirect(url_for("auth.register"))

    shop = Shop(shop_name=shop_name)
    db.session.add(shop)
    db.session.flush()

    owner = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role="owner",
        shop_id=shop.id
    )

    db.session.add(owner)
    db.session.commit()

    login_user(owner)

    return redirect(url_for("dashboard"))

@auth.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.is_active and check_password_hash(
            user.password_hash, password
        ):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(url_for("auth.login"))