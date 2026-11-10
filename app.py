from flask import Flask, render_template
from flask_login import LoginManager, login_required, current_user
from config import Config
from database.db import db
from database.models import Shop, User, VoiceProfile, Product, Customer, Sale
from routes.auth import auth
from routes.employees import employees
from routes.shop_data import shop_data
from flask_migrate import Migrate
from routes.voice import voice

login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(employees)
    app.register_blueprint(shop_data)
    app.register_blueprint(voice)

    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth)

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        shop_id = current_user.shop_id

        # Basic statistics
        products_count = Product.query.filter_by(
            shop_id=shop_id
        ).count()

        customers_count = Customer.query.filter_by(
            shop_id=shop_id
        ).count()

        total_sales = db.session.query(
            db.func.coalesce(db.func.sum(Sale.total_amount), 0)
        ).filter_by(
            shop_id=shop_id
        ).scalar()

        outstanding_balance = db.session.query(
            db.func.coalesce(
                db.func.sum(Customer.outstanding_balance), 0
            )
        ).filter_by(
            shop_id=shop_id
        ).scalar()

        # Low-stock products
        low_stock_products = Product.query.filter(
            Product.shop_id == shop_id,
            Product.low_stock_threshold.isnot(None),
            Product.stock_quantity <= Product.low_stock_threshold
        ).order_by(
            Product.stock_quantity.asc()
        ).limit(5).all()

        # Recent transactions
        recent_sales = Sale.query.filter_by(
            shop_id=shop_id
        ).order_by(
            Sale.created_at.desc()
        ).limit(5).all()

        return render_template(
            "dashboard.html",
            products_count=products_count,
            customers_count=customers_count,
            total_sales=total_sales,
            outstanding_balance=outstanding_balance,
            low_stock_products=low_stock_products,
            recent_sales=recent_sales
        )

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
