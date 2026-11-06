from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import IntegrityError
from database.db import db
from database.models import User
from services.permissions import owner_required

employees = Blueprint("employees", __name__)


@employees.route("/employees", methods=["GET"])
@owner_required
def employee_list():

    shop_employees = User.query.filter_by(
        shop_id=employees_current_shop_id(),
        role="employee"
    ).order_by(User.created_at.desc()).all()

    return render_template(
        "employees.html",
        employees=shop_employees
    )


@employees.route("/employees/add", methods=["POST"])
@owner_required
def add_employee():

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not username or not email or not password:
        flash("Please fill in all fields.")
        return redirect(url_for("employees.employee_list"))

    if len(password) < 8:
        flash("Password must contain at least 8 characters.")
        return redirect(url_for("employees.employee_list"))

    if User.query.filter_by(email=email).first():
        flash("This email is already registered.")
        return redirect(url_for("employees.employee_list"))

    employee = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role="employee",
        shop_id=employees_current_shop_id()
    )

    db.session.add(employee)

    try:
        db.session.commit()
        flash(f"Employee {username} added successfully!")
    except IntegrityError:
        db.session.rollback()
        flash("This email is already registered.")

    return redirect(url_for("employees.employee_list"))


@employees.route("/employees/<int:employee_id>/toggle", methods=["POST"])
@owner_required
def toggle_employee(employee_id):

    employee = User.query.filter_by(
        id=employee_id,
        shop_id=employees_current_shop_id(),
        role="employee"
    ).first_or_404()

    employee.is_active = not employee.is_active

    db.session.commit()

    status = "activated" if employee.is_active else "deactivated"

    flash(f"{employee.username} has been {status}.")

    return redirect(url_for("employees.employee_list"))


def employees_current_shop_id():
    from flask_login import current_user
    return current_user.shop_id