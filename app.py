from flask import Flask
from flask_login import LoginManager, login_required, current_user
from config import Config

from database.db import db
from database.models import Shop, User, VoiceProfile, Product, Customer
from routes.auth import auth
from routes.employees import employees
from routes.shop_data import shop_data
from flask_migrate import Migrate


login_manager = LoginManager()
migrate = Migrate()


def create_app():

    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(employees)
    app.register_blueprint(shop_data)

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
        return "DukaanSathi AI is running!"

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return f"Welcome {current_user.username}! Your shop is ready."

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)