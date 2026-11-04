import os
import re
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func

from models import Category, Transaction, User, db

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "info"
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__)
    os.makedirs(app.instance_path, exist_ok=True)

    db_url = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "expenses.db")
    )
    if db_url.startswith("postgres://"):  # Render/Heroku style URL
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_routes(app)

    with app.app_context():
        db.create_all()
    return app


# ---------------------------------------------------------------- helpers
def parse_month(value):
    """'YYYY-MM' -> (start_date, next_month_start, 'YYYY-MM'). Defaults to this month."""
    try:
        year, month = [int(x) for x in value.split("-")]
        start = date(year, month, 1)
    except (AttributeError, ValueError):
        today = date.today()
        start = date(today.year, today.month, 1)
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, end, start.strftime("%Y-%m")


def shift_month(start, delta):
    idx = start.year * 12 + (start.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def sum_by_type(user_id, start=None, end=None):
    q = db.session.query(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user_id
    )
    if start:
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    totals = {"income": 0.0, "expense": 0.0}
    for kind, total in q.group_by(Transaction.type).all():
        totals[kind] = float(total)
    totals["balance"] = totals["income"] - totals["expense"]
    return totals


def category_breakdown(user_id, kind, start, end):
    rows = (
        db.session.query(Category.name, func.sum(Transaction.amount))
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == kind,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    return [(name, float(total)) for name, total in rows]


def read_transaction_form(form):
    """Validate the add/edit form. Returns (data, error)."""
    kind = form.get("type")
    if kind not in ("income", "expense"):
        return None, "Choose income or expense."
    try:
        amount = Decimal(form.get("amount", "").strip()).quantize(Decimal("0.01"))
        if amount <= 0 or amount > Decimal("9999999999.99"):
            raise InvalidOperation
    except InvalidOperation:
        return None, "Enter a valid amount greater than zero."
    try:
        tx_date = datetime.strptime(form.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return None, "Enter a valid date."
    category = db.session.get(Category, int(form.get("category_id") or 0))
    if not category or category.user_id != current_user.id or category.type != kind:
        return None, "Choose a category that matches the transaction type."
    return {
        "type": kind,
        "amount": amount,
        "date": tx_date,
        "category_id": category.id,
        "description": form.get("description", "").strip()[:200],
    }, None


def user_categories():
    return (
        Category.query.filter_by(user_id=current_user.id)
        .order_by(Category.type, Category.name)
        .all()
    )


def is_strong_password(password):
    return bool(
        re.fullmatch(r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}", password or "")
    )


# ----------------------------------------------------------------- routes
def register_routes(app):
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    # ---- auth
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")
            if not name or not email or "@" not in email:
                flash("Enter your name and a valid email.", "error")
            elif not is_strong_password(password):
                flash(
                    "Password must be at least 8 characters and include uppercase, lowercase, number, and special characters.",
                    "error",
                )
            elif password != confirm:
                flash("Passwords do not match.", "error")
            elif User.query.filter_by(email=email).first():
                flash("That email is already registered.", "error")
            else:
                user = User(name=name, email=email)
                user.set_password(password)
                user.seed_categories()
                db.session.add(user)
                db.session.commit()
                login_user(user)
                flash("Welcome! Your account is ready.", "success")
                return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(request.form.get("password", "")):
                login_user(user, remember=bool(request.form.get("remember")))
                nxt = request.args.get("next", "")
                if not nxt.startswith("/") or nxt.startswith("//"):
                    nxt = url_for("dashboard")
                return redirect(nxt)
            flash("Invalid email or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    # ---- dashboard
    @app.route("/dashboard")
    @login_required
    def dashboard():
        uid = current_user.id
        start, end, ym = parse_month(None)
        overall = sum_by_type(uid)
        this_month = sum_by_type(uid, start, end)
        recent = (
            Transaction.query.filter_by(user_id=uid)
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(6)
            .all()
        )
        expense_cats = category_breakdown(uid, "expense", start, end)

        trend = OrderedDict()
        for i in range(5, -1, -1):
            m_start = shift_month(start, -i)
            m_end = shift_month(m_start, 1)
            t = sum_by_type(uid, m_start, m_end)
            trend[m_start.strftime("%b %Y")] = (t["income"], t["expense"])

        return render_template(
            "dashboard.html",
            overall=overall,
            this_month=this_month,
            recent=recent,
            month_label=start.strftime("%B %Y"),
            cat_labels=[c[0] for c in expense_cats],
            cat_values=[c[1] for c in expense_cats],
            trend_labels=list(trend.keys()),
            trend_income=[v[0] for v in trend.values()],
            trend_expense=[v[1] for v in trend.values()],
        )

    # ---- transactions
    @app.route("/transactions")
    @login_required
    def transactions():
        q = Transaction.query.filter_by(user_id=current_user.id)
        month = request.args.get("month", "")
        kind = request.args.get("type", "")
        cat = request.args.get("category", type=int)
        if month:
            start, end, month = parse_month(month)
            q = q.filter(Transaction.date >= start, Transaction.date < end)
        if kind in ("income", "expense"):
            q = q.filter(Transaction.type == kind)
        if cat:
            q = q.filter(Transaction.category_id == cat)

        page = request.args.get("page", 1, type=int)
        pagination = q.order_by(Transaction.date.desc(), Transaction.id.desc()).paginate(
            page=page, per_page=15, error_out=False
        )
        filtered_totals = {"income": 0.0, "expense": 0.0}
        for t_kind, total in (
            q.with_entities(Transaction.type, func.sum(Transaction.amount))
            .group_by(Transaction.type)
            .all()
        ):
            filtered_totals[t_kind] = float(total or 0)

        return render_template(
            "transactions.html",
            pagination=pagination,
            categories=user_categories(),
            filters={"month": month, "type": kind, "category": cat},
            filtered_totals=filtered_totals,
        )

    @app.route("/transactions/add", methods=["GET", "POST"])
    @login_required
    def add_transaction():
        if request.method == "POST":
            data, error = read_transaction_form(request.form)
            if error:
                flash(error, "error")
            else:
                db.session.add(Transaction(user_id=current_user.id, **data))
                db.session.commit()
                flash("Transaction added.", "success")
                return redirect(url_for("transactions"))
        preset = request.args.get("type", "expense")
        return render_template(
            "transaction_form.html",
            tx=None,
            categories=user_categories(),
            preset_type=preset if preset in ("income", "expense") else "expense",
            today=date.today().isoformat(),
        )

    @app.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_transaction(tx_id):
        tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
        if request.method == "POST":
            data, error = read_transaction_form(request.form)
            if error:
                flash(error, "error")
            else:
                for key, value in data.items():
                    setattr(tx, key, value)
                db.session.commit()
                flash("Transaction updated.", "success")
                return redirect(url_for("transactions"))
        return render_template(
            "transaction_form.html",
            tx=tx,
            categories=user_categories(),
            preset_type=tx.type,
            today=date.today().isoformat(),
        )

    @app.route("/transactions/<int:tx_id>/delete", methods=["POST"])
    @login_required
    def delete_transaction(tx_id):
        tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
        db.session.delete(tx)
        db.session.commit()
        flash("Transaction deleted.", "info")
        return redirect(request.referrer or url_for("transactions"))

    # ---- categories
    @app.route("/categories", methods=["GET", "POST"])
    @login_required
    def categories():
        if request.method == "POST":
            name = request.form.get("name", "").strip()[:60]
            kind = request.form.get("type")
            if not name or kind not in ("income", "expense"):
                flash("Enter a category name and type.", "error")
            elif Category.query.filter_by(user_id=current_user.id, name=name, type=kind).first():
                flash("That category already exists.", "error")
            else:
                db.session.add(Category(user_id=current_user.id, name=name, type=kind))
                db.session.commit()
                flash("Category added.", "success")
            return redirect(url_for("categories"))
        return render_template("categories.html", categories=user_categories())

    @app.route("/categories/<int:cat_id>/delete", methods=["POST"])
    @login_required
    def delete_category(cat_id):
        cat = Category.query.filter_by(id=cat_id, user_id=current_user.id).first_or_404()
        if Transaction.query.filter_by(category_id=cat.id).first():
            flash("This category has transactions. Move or delete them first.", "error")
        else:
            db.session.delete(cat)
            db.session.commit()
            flash("Category deleted.", "info")
        return redirect(url_for("categories"))

    # ---- monthly report
    @app.route("/report")
    @login_required
    def report():
        uid = current_user.id
        start, end, ym = parse_month(request.args.get("month"))
        prev_start = shift_month(start, -1)
        totals = sum_by_type(uid, start, end)
        prev = sum_by_type(uid, prev_start, start)
        savings_rate = (totals["balance"] / totals["income"] * 100) if totals["income"] else None

        daily = (
            db.session.query(Transaction.date, func.sum(Transaction.amount))
            .filter(
                Transaction.user_id == uid,
                Transaction.type == "expense",
                Transaction.date >= start,
                Transaction.date < end,
            )
            .group_by(Transaction.date)
            .all()
        )
        daily_map = {d: float(a) for d, a in daily}
        days_in_month = (end - start).days
        day_labels = [str(i + 1) for i in range(days_in_month)]
        day_values = [daily_map.get(date(start.year, start.month, i + 1), 0.0) for i in range(days_in_month)]

        expense_cats = category_breakdown(uid, "expense", start, end)
        income_cats = category_breakdown(uid, "income", start, end)
        biggest = (
            Transaction.query.filter(
                Transaction.user_id == uid,
                Transaction.type == "expense",
                Transaction.date >= start,
                Transaction.date < end,
            )
            .order_by(Transaction.amount.desc())
            .first()
        )
        return render_template(
            "report.html",
            ym=ym,
            month_label=start.strftime("%B %Y"),
            prev_ym=prev_start.strftime("%Y-%m"),
            next_ym=end.strftime("%Y-%m"),
            totals=totals,
            prev=prev,
            savings_rate=savings_rate,
            expense_cats=expense_cats,
            income_cats=income_cats,
            day_labels=day_labels,
            day_values=day_values,
            biggest=biggest,
            tx_count=Transaction.query.filter(
                Transaction.user_id == uid, Transaction.date >= start, Transaction.date < end
            ).count(),
        )

    @app.template_filter("money")
    def money(value):
        return f"{float(value or 0):,.2f}"

    @app.context_processor
    def inject_globals():
        return {"currency": os.environ.get("CURRENCY_SYMBOL", "₹")}


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
