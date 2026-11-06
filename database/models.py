from flask_migrate import Migrate

from database.db import db
from flask_login import UserMixin
from datetime import datetime


class Shop(db.Model):

    id = db.Column(db.Integer, primary_key = True)
    shop_name = db.Column(db.String(100), nullable = False)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)
    users = db.relationship("User", backref="shop", lazy = True)
    products = db.relationship("Product", backref="shop", lazy = True)
    customers = db.relationship("Customer", backref = "shop", lazy = True)

class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(100), nullable = False)
    email = db.Column(db.String(250), nullable = False, unique = True)
    password_hash = db.Column(db.String(250), nullable = False)
    role = db.Column(db.String(100), default="employee", nullable = False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable = True)
    is_active = db.Column(db.Boolean, default = True)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)
    voice_profiles = db.relationship("VoiceProfile", backref="user", uselist = True)

class VoiceProfile(db.Model):

    id = db.Column(db.Integer, primary_key = True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable = False)
    embedding_path = db.Column(db.String(256), nullable = False)
    is_verified = db.Column(db.Boolean, default = False)

class Product(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    stock_quantity = db.Column(db.Numeric(12, 3),nullable=False,default=0)
    low_stock_threshold = db.Column(db.Numeric(12, 3),nullable=True)
    packs = db.relationship("ProductPack",backref="product",lazy=True,cascade="all, delete-orphan")
    shop_id = db.Column(db.Integer,db.ForeignKey("shop.id"),nullable=False)
    created_at = db.Column(db.DateTime,default=datetime.utcnow)

class ProductPack(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer,db.ForeignKey("product.id"),nullable=False)
    pack_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime,default=datetime.utcnow)

class Customer(db.Model):

    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(100), nullable = False)
    phone = db.Column(db.String(15), nullable = True)
    outstanding_balance = db.Column(db.Numeric(10,2), default = 0)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable = False)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)

