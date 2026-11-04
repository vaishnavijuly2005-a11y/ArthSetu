# 💸 Smart Expense Tracker

A multi-user expense tracker built with **Flask**, **SQLAlchemy** and **Chart.js**.

## Features

- Register / login / logout (hashed passwords, CSRF protection, per-user data)
- Add, edit and delete **income** and **expenses** with **categories** (defaults are created for every new user; add or delete your own)
- **Dashboard**: total income, total expenses, balance, this month's summary, spending-by-category chart, 6-month trend, recent transactions
- **Transaction history** with filters (month, type, category) and pagination
- **Monthly report**: income vs expenses, savings rate, comparison with last month, daily spending chart, category breakdown
- **Database**: SQLite locally (zero setup), PostgreSQL in production (via `DATABASE_URL`)

## Project structure

```
smart-expense-tracker/
├── app.py              # Flask app factory + all routes
├── models.py           # User, Category, Transaction models
├── requirements.txt
├── Procfile            # gunicorn start command
├── render.yaml         # one-click Render deploy (web service + PostgreSQL)
├── .env.example        # environment variable template
├── templates/          # Jinja2 pages
├── static/style.css
└── tests/test_app.py   # pytest tests
```

---

## Step 1 — Run it locally

Requires Python 3.10+.

```bash
cd smart-expense-tracker
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000, click **Register**, and start adding transactions.
The SQLite database is created automatically in `instance/expenses.db`.

Optional: run the tests

```bash
pip install pytest
pytest
```

---

## Step 2 — Push the code to GitHub

1. Create a GitHub account at https://github.com if you don't have one.
2. Create an **empty** repository: **New repository** → name it `smart-expense-tracker` → leave "Add README / .gitignore" **unchecked** → **Create repository**.
3. Install Git (https://git-scm.com) and set your identity once:
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
4. In the project folder run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Smart Expense Tracker"
   git branch -M main
   git remote add origin https://github.com/<your-username>/smart-expense-tracker.git
   git push -u origin main
   ```
   When asked for a password, use a **Personal Access Token** (GitHub → Settings → Developer settings → Personal access tokens), or sign in through GitHub Desktop / `gh auth login`.

`.gitignore` already keeps your local database, virtual environment and `.env` out of the repo.

---

## Step 3 — Deploy online (free)

> **Note:** GitHub Pages only hosts static sites, so it cannot run a Flask app. GitHub stores your code; a host such as **Render** runs it straight from your GitHub repo.

### Option A: Render (recommended, uses `render.yaml`)

1. Sign up at https://render.com with your GitHub account.
2. **New +** → **Blueprint** → select your `smart-expense-tracker` repo → **Apply**.
3. Render creates the web service **and** a PostgreSQL database, wires `DATABASE_URL`, and generates `SECRET_KEY` automatically.
4. After the build finishes, open the `https://smart-expense-tracker-xxxx.onrender.com` URL and register.

Every `git push` to `main` redeploys automatically.

Free-tier notes: the web service sleeps after inactivity (first load takes ~30–60 s), and Render's free PostgreSQL databases expire after a limited period, so check their current free-plan terms before relying on it for real data.

### Option B: Manual setup on Render (without the blueprint)

1. **New +** → **PostgreSQL** → create it, then copy the **Internal Database URL**.
2. **New +** → **Web Service** → connect your repo and set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Environment variables: `SECRET_KEY` (a long random string), `DATABASE_URL` (the URL from step 1)

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs sessions and CSRF tokens. **Set this in production.** | insecure dev value |
| `DATABASE_URL` | PostgreSQL connection string | local SQLite file |
| `CURRENCY_SYMBOL` | Symbol shown before amounts | `₹` |

---

## How it works (short)

- Each user owns their own categories and transactions; every query is filtered by the logged-in user, and other users' records return 404.
- Amounts are stored as `Numeric(12,2)`; the form validates amount, date and that the category matches the transaction type.
- Tables are created automatically on startup (`db.create_all()`). For future schema changes, consider adding Flask-Migrate.

## Ideas to extend

CSV export, recurring transactions, monthly budgets per category, password reset by email.
