from datetime import date, datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

DEFAULT_CATEGORIES = {
    "income": ["Salary", "Freelance", "Investments", "Gift", "Other Income"],
    "expense": [
        "Food & Dining",
        "Rent",
        "Transport",
        "Utilities",
        "Shopping",
        "Health",
        "Entertainment",
        "Education",
        "Other",
    ],
}


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    categories = db.relationship(
        "Category", backref="user", cascade="all, delete-orphan", lazy=True
    )
    transactions = db.relationship(
        "Transaction", backref="user", cascade="all, delete-orphan", lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def seed_categories(self):
        for kind, names in DEFAULT_CATEGORIES.items():
            for name in names:
                self.categories.append(Category(name=name, type=kind))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # "income" or "expense"

    __table_args__ = (db.UniqueConstraint("user_id", "name", "type", name="uq_user_cat"),)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # "income" or "expense"
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(200), default="")
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    category = db.relationship("Category")
