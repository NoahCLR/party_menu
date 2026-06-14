from __future__ import annotations

import csv
import functools
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE = DATA_DIR / "menu.db"

DEFAULT_CATEGORIES = (
    "Cocktails",
    "Booze, Beer & Wine",
    "Hard Drinks",
    "Soft Drinks",
    "Snacks",
)
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
CATALOG_VERSION = "3"
PUSHOVER_MESSAGES_URL = "https://api.pushover.net/1/messages.json"
UNASSIGNED_CATEGORY = "Unassigned"
GUEST_NAME_COOKIE = "party_guest_name"
GUEST_NAME_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
EXPORT_FORMAT_VERSION = 1
MENU_EXPORT_COLUMNS = (
    "name",
    "description",
    "category",
    "available",
    "image_url",
    "image_filename",
    "category_order",
    "sort_order",
)


class PushoverError(RuntimeError):
    pass

SEED_ITEMS = (
    (
        "Espresso Martini",
        "Vodka, espresso, and coffee liqueur.",
        "Cocktails",
        "/static/seed/espresso-martini.jpg",
        1,
    ),
    (
        "Whiskey Sour",
        "Whiskey, fresh lemon, and sugar.",
        "Cocktails",
        "/static/seed/whiskey-sour.jpg",
        1,
    ),
    (
        "Mudslide",
        "Vodka, coffee liqueur, cream liqueur, and cream.",
        "Cocktails",
        "/static/seed/mudslide.jpg",
        1,
    ),
    (
        "White Russian",
        "Vodka, coffee liqueur, and cream.",
        "Cocktails",
        "/static/seed/white-russian.jpg",
        1,
    ),
    (
        "Pornstar Martini",
        "Vodka, passion fruit, vanilla, and lime.",
        "Cocktails",
        "/static/seed/pornstar-martini.jpg",
        1,
    ),
    (
        "Lemon Pie",
        "A sweet and creamy lemon cocktail.",
        "Cocktails",
        "/static/seed/lemon-pie.jpg",
        1,
    ),
    (
        "Moscow Mule",
        "Vodka, ginger beer, and fresh lime.",
        "Cocktails",
        "/static/seed/moscow-mule.jpg",
        1,
    ),
    (
        "Gin & Tonic",
        "Gin, tonic, and fresh citrus.",
        "Cocktails",
        "/static/seed/gin-tonic.jpg",
        1,
    ),
    (
        "Sangria",
        "Wine, fruit, and citrus.",
        "Cocktails",
        "/static/seed/sangria.jpg",
        1,
    ),
    (
        "White Wine - Pinot Grigio",
        "Crisp and refreshing white wine.",
        "Booze, Beer & Wine",
        "/static/seed/pinot-grigio.jpg",
        1,
    ),
    (
        "Red Wine - Cabernet Sauvignon",
        "A full-bodied red wine.",
        "Booze, Beer & Wine",
        "/static/seed/cabernet-sauvignon.jpg",
        1,
    ),
    ("Vodka", "Available neat or over ice.", "Hard Drinks", "/static/seed/vodka.jpg", 1),
    ("Whiskey", "Available neat or over ice.", "Hard Drinks", "/static/seed/whiskey.jpg", 1),
    ("Rum", "Available neat or over ice.", "Hard Drinks", "/static/seed/rum.jpg", 1),
    ("Gin", "Available neat or over ice.", "Hard Drinks", "/static/seed/gin.jpg", 1),
    ("Cola", "Served chilled.", "Soft Drinks", "/static/seed/cola.jpg", 1),
    ("Fanta", "Served chilled.", "Soft Drinks", "/static/seed/fanta.jpg", 1),
    ("Iced Tea - Green", "Served chilled.", "Soft Drinks", "/static/seed/iced-tea-green.jpg", 1),
    ("Iced Tea - Peach", "Served chilled.", "Soft Drinks", "/static/seed/iced-tea-peach.jpg", 1),
    (
        "Cashew Nuts",
        "Roasted cashew nuts.",
        "Snacks",
        "/static/seed/cashew-nuts.jpg",
        1,
    ),
    (
        "Pistachio Nuts",
        "Roasted pistachio nuts.",
        "Snacks",
        "/static/seed/pistachio-nuts.jpg",
        1,
    ),
    (
        "Naturel Chips",
        "Classic salted potato chips.",
        "Snacks",
        "/static/seed/naturel-chips.jpg",
        1,
    ),
    (
        "Paprika Chips",
        "Paprika-seasoned potato chips.",
        "Snacks",
        "/static/seed/paprika-chips.jpg",
        1,
    ),
    (
        "Garlic Olives",
        "Olives marinated with garlic.",
        "Snacks",
        "/static/seed/garlic-olives.jpg",
        1,
    ),
    (
        "Jonge Kaasblokjes",
        "Cubes of young Dutch cheese.",
        "Snacks",
        "/static/seed/jonge-kaasblokjes.jpg",
        1,
    ),
)

LEGACY_SEED_ITEMS = (
    ("Negroni", "/static/seed/negroni.jpg"),
    ("Paloma", "/static/seed/paloma.jpg"),
    ("Cold Beer", "/static/seed/cold-beer.jpg"),
    ("Red Wine", "/static/seed/red-wine.jpg"),
    ("Olives", "/static/seed/olives.jpg"),
    ("Crisps", "/static/seed/crisps.jpg"),
    ("Cheese Board", "/static/seed/cheese-board.jpg"),
)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "change-me-tonight"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").casefold() == "true",
        PUSHOVER_API_TOKEN=os.environ.get("PUSHOVER_API_TOKEN", ""),
        PUSHOVER_USER_KEY=os.environ.get("PUSHOVER_USER_KEY", ""),
        PUSHOVER_API_URL=os.environ.get("PUSHOVER_API_URL", PUSHOVER_MESSAGES_URL),
        ORDER_COOLDOWN_SECONDS=5,
    )
    if test_config:
        app.config.update(test_config)

    data_dir = Path(app.config.get("DATA_DIR", DATA_DIR))
    upload_dir = data_dir / "uploads"
    database = data_dir / "menu.db"
    app.config.update(DATA_DIR=data_dir, UPLOAD_DIR=upload_dir, DATABASE=database)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    upload_dir.mkdir(parents=True, exist_ok=True)

    app.teardown_appcontext(close_db)
    app.jinja_env.globals.update(csrf_token=csrf_token, static_asset=static_asset)

    with app.app_context():
        init_db()

    register_routes(app)
    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 10000")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def static_asset(filename: str) -> str:
    path = BASE_DIR / "static" / filename
    try:
        version = path.stat().st_mtime_ns
    except OSError:
        version = CATALOG_VERSION
    return url_for("static", filename=filename, v=version)


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            image TEXT NOT NULL DEFAULT '',
            available INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS menu_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.execute("BEGIN IMMEDIATE")
    categories_initialized = db.execute(
        "SELECT value FROM app_meta WHERE key = 'categories_initialized'"
    ).fetchone()
    if categories_initialized is None:
        category_count = db.execute(
            "SELECT COUNT(*) FROM menu_categories"
        ).fetchone()[0]
        if category_count == 0:
            db.executemany(
                "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
                [
                    (category, sort_order)
                    for sort_order, category in enumerate(DEFAULT_CATEGORIES, start=1)
                ],
            )
        db.execute(
            "INSERT INTO app_meta (key, value) VALUES ('categories_initialized', '1')"
        )
    next_category_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM menu_categories"
    ).fetchone()[0]
    legacy_categories = db.execute(
        """
        SELECT DISTINCT menu_items.category
        FROM menu_items
        LEFT JOIN menu_categories
            ON menu_categories.name = menu_items.category COLLATE NOCASE
        WHERE menu_categories.id IS NULL
            AND TRIM(menu_items.category) != ''
            AND menu_items.category != ? COLLATE NOCASE
        ORDER BY menu_items.category COLLATE NOCASE
        """,
        (UNASSIGNED_CATEGORY,),
    ).fetchall()
    for row in legacy_categories:
        next_category_order += 1
        db.execute(
            "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
            (row["category"], next_category_order),
        )
    category_names = db.execute("SELECT name FROM menu_categories").fetchall()
    for row in category_names:
        db.execute(
            """
            UPDATE menu_items
            SET category = ?
            WHERE category = ? COLLATE NOCASE AND category != ?
            """,
            (row["name"], row["name"], row["name"]),
        )
    count = db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
    catalog_version_row = db.execute(
        "SELECT value FROM app_meta WHERE key = 'catalog_version'"
    ).fetchone()
    catalog_version = int(catalog_version_row["value"]) if catalog_version_row else 0
    if catalog_version < 2:
        if count:
            db.executemany(
                "DELETE FROM menu_items WHERE name = ? AND image = ?",
                LEGACY_SEED_ITEMS,
            )
        next_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM menu_items"
        ).fetchone()[0]
        for item in SEED_ITEMS:
            existing = db.execute(
                "SELECT 1 FROM menu_items WHERE name = ? AND category = ?",
                (item[0], item[2]),
            ).fetchone()
            if existing:
                continue
            next_order += 1
            db.execute(
                """
                INSERT INTO menu_items
                    (name, description, category, image, available, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (*item, next_order),
            )
    if catalog_version < 3:
        db.executemany(
            """
            UPDATE menu_items
            SET image = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ? AND category = ? AND image = ''
            """,
            [(item[3], item[0], item[2]) for item in SEED_ITEMS],
        )
    db.execute(
        """
        INSERT INTO app_meta (key, value) VALUES ('catalog_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (CATALOG_VERSION,),
    )
    db.commit()


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def require_csrf() -> None:
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        abort(400, "Invalid form token. Refresh the page and try again.")


def host_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("host_logged_in"):
            return redirect(url_for("host_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def get_category_rows() -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT id, name, sort_order FROM menu_categories ORDER BY sort_order, id"
    ).fetchall()


def get_categories() -> list[str]:
    return [row["name"] for row in get_category_rows()]


def clean_category_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def category_name_error(name: str) -> str | None:
    if not name:
        return "Category name is required."
    if len(name) > 80:
        return "Category names may not exceed 80 characters."
    if name.casefold() == "all items":
        return "All items is reserved for the editor filter."
    if name.casefold() == UNASSIGNED_CATEGORY.casefold():
        return f"{UNASSIGNED_CATEGORY} is reserved for hidden items."
    return None


def canonical_category(value: str) -> str | None:
    display_name = clean_category_name(value)
    if not display_name:
        return None
    if display_name.casefold() == UNASSIGNED_CATEGORY.casefold():
        return UNASSIGNED_CATEGORY
    existing = get_db().execute(
        "SELECT name FROM menu_categories WHERE name = ? COLLATE NOCASE",
        (display_name,),
    ).fetchone()
    if existing:
        return existing["name"]
    cleaned = display_name.casefold()
    aliases = {
        "booze": "Booze, Beer & Wine",
        "beer": "Booze, Beer & Wine",
        "wine": "Booze, Beer & Wine",
        "drinks": "Booze, Beer & Wine",
        "hard drink": "Hard Drinks",
        "hard drinks": "Hard Drinks",
        "spirits": "Hard Drinks",
        "soft drink": "Soft Drinks",
        "soft drinks": "Soft Drinks",
        "soda": "Soft Drinks",
        "snack": "Snacks",
        "cocktail": "Cocktails",
    }
    alias = aliases.get(cleaned)
    if not alias:
        return None
    existing = get_db().execute(
        "SELECT name FROM menu_categories WHERE name = ? COLLATE NOCASE",
        (alias,),
    ).fetchone()
    return existing["name"] if existing else None


def parse_available(value: str | None, default: bool = True) -> int:
    if value is None or value == "":
        return int(default)
    return int(str(value).strip().casefold() not in {"0", "false", "no", "out", "sold out"})


def clean_guest_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())[:80]


def clean_image_reference(value: str | None) -> str:
    value = (value or "").strip()
    if value.startswith(("https://", "http://", "/uploads/", "/static/")):
        return value
    return ""


def save_image_bytes(filename: str, payload: bytes) -> str:
    original = secure_filename(filename)
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image type: {extension or 'unknown'}")
    if not payload or len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("Each image must be between 1 byte and 10 MB.")
    stem = secure_filename(Path(original).stem)[:60] or "menu-item"
    stored_name = f"{stem}-{uuid.uuid4().hex[:10]}{extension}"
    destination = Path(current_app_upload_dir()) / stored_name
    destination.write_bytes(payload)
    return f"/uploads/{stored_name}"


def current_app_upload_dir() -> Path:
    return current_app.config["UPLOAD_DIR"]


def save_uploaded_image(upload) -> str:
    if not upload or not upload.filename:
        return ""
    return save_image_bytes(upload.filename, upload.read())


def delete_uploaded_image(image: str) -> None:
    if not image.startswith("/uploads/"):
        return
    db = get_db()
    in_use = db.execute("SELECT COUNT(*) FROM menu_items WHERE image = ?", (image,)).fetchone()[0]
    if in_use:
        return
    path = Path(current_app_upload_dir()) / Path(image).name
    path.unlink(missing_ok=True)


def category_order_sql() -> str:
    return """
        COALESCE(
            (SELECT sort_order FROM menu_categories
             WHERE name = menu_items.category COLLATE NOCASE),
            2147483647
        )
    """


def normalize_category_order(db: sqlite3.Connection, category: str) -> None:
    rows = db.execute(
        "SELECT id FROM menu_items WHERE category = ? ORDER BY sort_order, id",
        (category,),
    ).fetchall()
    db.executemany(
        "UPDATE menu_items SET sort_order = ? WHERE id = ?",
        [(index, row["id"]) for index, row in enumerate(rows, start=1)],
    )


def normalize_category_positions(db: sqlite3.Connection) -> None:
    rows = db.execute(
        "SELECT id FROM menu_categories ORDER BY sort_order, id"
    ).fetchall()
    db.executemany(
        "UPDATE menu_categories SET sort_order = ? WHERE id = ?",
        [(index, row["id"]) for index, row in enumerate(rows, start=1)],
    )


def send_pushover_order(
    item_name: str, category: str, guest_name: str, note: str
) -> None:
    token = current_app.config["PUSHOVER_API_TOKEN"]
    user_key = current_app.config["PUSHOVER_USER_KEY"]
    if not token or not user_key:
        raise PushoverError("Pushover credentials are not configured.")

    payload = urlencode(
        {
            "token": token,
            "user": user_key,
            "title": f"Order from {guest_name}",
            "message": (
                f"Item: {item_name}\nCategory: {category}"
                + (f"\nNote: {note}" if note else "")
            ),
        }
    ).encode("utf-8")
    pushover_request = Request(
        current_app.config["PUSHOVER_API_URL"],
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(pushover_request, timeout=5) as response:
            response_data = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise PushoverError("Pushover request failed.") from error

    if response_data.get("status") != 1:
        raise PushoverError("Pushover rejected the message.")


def register_routes(app: Flask) -> None:
    @app.before_request
    def check_csrf():
        if request.method == "POST":
            require_csrf()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: http: https:; "
            "script-src 'self'; style-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/")
    def menu():
        categories = get_categories()
        rows = get_db().execute(
            f"""
            SELECT * FROM menu_items
            WHERE category != ? COLLATE NOCASE
            ORDER BY {category_order_sql()}, sort_order, id
            """,
            (UNASSIGNED_CATEGORY,),
        ).fetchall()
        grouped = {category: [] for category in categories}
        for row in rows:
            grouped.setdefault(row["category"], []).append(row)
        available_count = sum(row["available"] for row in rows)
        return render_template(
            "menu.html",
            grouped=grouped,
            categories=categories,
            available_count=available_count,
            total_count=len(rows),
        )

    @app.get("/health")
    def health():
        get_db().execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.route("/order/item/<int:item_id>", methods=("GET", "POST"))
    def order_item(item_id: int):
        item = get_db().execute(
            "SELECT name, description, category, available FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            abort(404)
        if item["category"].casefold() == UNASSIGNED_CATEGORY.casefold():
            abort(404)
        if not item["available"]:
            flash(f"{item['name']} is currently out.", "error")
            return redirect(url_for("menu"))

        if request.method == "GET":
            guest_name = clean_guest_name(request.cookies.get(GUEST_NAME_COOKIE))
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=""
            )

        submitted_guest_name = " ".join(
            request.form.get("guest_name", "").strip().split()
        )
        guest_name = clean_guest_name(submitted_guest_name)
        note = request.form.get("note", "").strip()
        if not guest_name:
            flash("Enter your name before sending the order.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 400
        if len(submitted_guest_name) > 80:
            flash("Your name may not exceed 80 characters.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 400
        if len(note) > 300:
            flash("The note may not exceed 300 characters.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 400

        now = time.time()
        last_order_at = session.get("last_order_at", 0)
        if now - last_order_at < current_app.config["ORDER_COOLDOWN_SECONDS"]:
            flash("Please wait a few seconds before ordering again.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 429

        try:
            send_pushover_order(item["name"], item["category"], guest_name, note)
        except PushoverError as error:
            current_app.logger.warning("Could not send order: %s", error)
            flash("The order could not be sent. Please tell the host.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 502
        else:
            session["last_order_at"] = now
            flash(f"Order sent for {guest_name}: {item['name']}.", "success")
        response = redirect(url_for("menu"))
        response.set_cookie(
            GUEST_NAME_COOKIE,
            guest_name,
            max_age=GUEST_NAME_COOKIE_MAX_AGE,
            httponly=True,
            secure=current_app.config["SESSION_COOKIE_SECURE"] or request.is_secure,
            samesite="Lax",
        )
        return response

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename: str):
        return send_from_directory(app.config["UPLOAD_DIR"], filename)

    @app.route("/host/login", methods=("GET", "POST"))
    def host_login():
        if request.method == "POST":
            password = request.form.get("password", "")
            expected = app.config["ADMIN_PASSWORD"]
            if hmac.compare_digest(password, expected):
                session.clear()
                session["host_logged_in"] = True
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("host_editor"))
            flash("That password is not correct.", "error")
        return render_template("login.html")

    @app.post("/host/logout")
    @host_required
    def host_logout():
        session.clear()
        return redirect(url_for("menu"))

    @app.get("/host")
    @host_required
    def host_editor():
        category_rows = [dict(row) for row in get_category_rows()]
        for index, category_row in enumerate(category_rows):
            category_row["can_move_up"] = index > 0
            category_row["can_move_down"] = index < len(category_rows) - 1
        categories = [row["name"] for row in category_rows]
        editor_categories = [*categories, UNASSIGNED_CATEGORY]
        selected_category = request.args.get("category", "All items")
        selected_status = request.args.get("status", "all")
        conditions = []
        values = []
        if selected_category in editor_categories:
            conditions.append("category = ?")
            values.append(selected_category)
        if selected_status in {"available", "out"}:
            conditions.append("available = ?")
            values.append(int(selected_status == "available"))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = get_db().execute(
            f"SELECT * FROM menu_items {where} ORDER BY {category_order_sql()}, sort_order, id",
            values,
        ).fetchall()
        db = get_db()
        all_rows = db.execute("SELECT id, category, available FROM menu_items").fetchall()
        for category_row in category_rows:
            category_row["item_count"] = sum(
                row["category"] == category_row["name"] for row in all_rows
            )
        counts = {
            "all": len(all_rows),
            "available": sum(row["available"] for row in all_rows),
            "out": sum(not row["available"] for row in all_rows),
            **{
                category: sum(row["category"] == category for row in all_rows)
                for category in editor_categories
            },
        }
        order_rows = db.execute(
            f"SELECT id, category FROM menu_items ORDER BY {category_order_sql()}, sort_order, id"
        ).fetchall()
        category_ids = {category: [] for category in editor_categories}
        for row in order_rows:
            category_ids.setdefault(row["category"], []).append(row["id"])
        positions = {
            item_id: (index, len(ids))
            for ids in category_ids.values()
            for index, item_id in enumerate(ids)
        }
        items_for_template = []
        for row in rows:
            item = dict(row)
            position, category_count = positions[item["id"]]
            item["can_move_up"] = position > 0
            item["can_move_down"] = position < category_count - 1
            items_for_template.append(item)
        items_json = items_for_template
        return render_template(
            "host.html",
            items=items_for_template,
            items_json=items_json,
            counts=counts,
            categories=categories,
            editor_categories=editor_categories,
            category_rows=category_rows,
            unassigned_category=UNASSIGNED_CATEGORY,
            default_item_category=(
                selected_category
                if selected_category in editor_categories
                else categories[0] if categories else UNASSIGNED_CATEGORY
            ),
            selected_category=selected_category,
            selected_status=selected_status,
        )

    @app.post("/host/item/save")
    @host_required
    def save_item():
        item_id = request.form.get("item_id", type=int)
        name = " ".join(request.form.get("name", "").strip().split())
        description = request.form.get("description", "").strip()
        category = canonical_category(request.form.get("category", ""))
        available = int(request.form.get("available") == "1")
        image_url = clean_image_reference(request.form.get("image_url"))
        existing_image = clean_image_reference(request.form.get("existing_image"))

        if not name or not category:
            flash("Name and category are required.", "error")
            return redirect(url_for("host_editor"))

        try:
            uploaded_image = save_uploaded_image(request.files.get("image_file"))
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("host_editor"))
        image = uploaded_image or image_url or existing_image

        db = get_db()
        if item_id:
            old = db.execute(
                "SELECT image, category, sort_order FROM menu_items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if old is None:
                abort(404)
            sort_order = old["sort_order"]
            if old["category"] != category:
                sort_order = db.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menu_items WHERE category = ?",
                    (category,),
                ).fetchone()[0]
            db.execute(
                """
                UPDATE menu_items
                SET name = ?, description = ?, category = ?, image = ?, available = ?, sort_order = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, description, category, image, available, sort_order, item_id),
            )
            if old["category"] != category:
                normalize_category_order(db, old["category"])
                normalize_category_order(db, category)
            db.commit()
            if old["image"] != image:
                delete_uploaded_image(old["image"])
            flash(f"Updated {name}.", "success")
        else:
            next_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menu_items WHERE category = ?",
                (category,),
            ).fetchone()[0]
            db.execute(
                """
                INSERT INTO menu_items
                    (name, description, category, image, available, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, description, category, image, available, next_order),
            )
            db.commit()
            flash(f"Added {name}.", "success")
        return redirect(url_for("host_editor"))

    @app.post("/host/category/save")
    @host_required
    def save_category():
        name = clean_category_name(request.form.get("name", ""))
        error = category_name_error(name)
        if error:
            flash(error, "error")
            return redirect(url_for("host_editor"))

        db = get_db()
        existing = db.execute(
            "SELECT name FROM menu_categories WHERE name = ? COLLATE NOCASE",
            (name,),
        ).fetchone()
        if existing:
            flash(f"Category {existing['name']} already exists.", "error")
            return redirect(url_for("host_editor", category=existing["name"]))

        next_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menu_categories"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
            (name, next_order),
        )
        db.commit()
        flash(f"Added category {name}.", "success")
        return redirect(url_for("host_editor", category=name))

    @app.post("/host/category/<int:category_id>/rename")
    @host_required
    def rename_category(category_id: int):
        name = clean_category_name(request.form.get("name", ""))
        error = category_name_error(name)
        if error:
            flash(error, "error")
            return redirect(url_for("host_editor", manage_categories="1"))

        db = get_db()
        category = db.execute(
            "SELECT id, name FROM menu_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if category is None:
            abort(404)

        existing = db.execute(
            "SELECT name FROM menu_categories WHERE name = ? COLLATE NOCASE AND id != ?",
            (name, category_id),
        ).fetchone()
        if existing:
            flash(f"Category {existing['name']} already exists.", "error")
            return redirect(url_for("host_editor", manage_categories="1"))

        old_name = category["name"]
        if name == old_name:
            return redirect(url_for("host_editor", manage_categories="1"))

        db.execute(
            "UPDATE menu_categories SET name = ? WHERE id = ?",
            (name, category_id),
        )
        db.execute(
            """
            UPDATE menu_items
            SET category = ?, updated_at = CURRENT_TIMESTAMP
            WHERE category = ? COLLATE NOCASE
            """,
            (name, old_name),
        )
        db.commit()
        flash(f"Renamed category {old_name} to {name}.", "success")
        return redirect(url_for("host_editor", category=name, manage_categories="1"))

    @app.post("/host/category/<int:category_id>/delete")
    @host_required
    def delete_category(category_id: int):
        db = get_db()
        category = db.execute(
            "SELECT id, name FROM menu_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if category is None:
            abort(404)

        items = db.execute(
            """
            SELECT id, image FROM menu_items
            WHERE category = ? COLLATE NOCASE
            ORDER BY sort_order, id
            """,
            (category["name"],),
        ).fetchall()
        item_action = request.form.get("item_action", "")
        if not items:
            item_action = "delete"
        if item_action not in {"delete", "existing", "new", "unassigned"}:
            flash("Choose what should happen to the category's items.", "error")
            return redirect(url_for("host_editor", manage_categories="1"))

        target_category = None
        if item_action == "existing":
            requested_target = clean_category_name(
                request.form.get("target_category", "")
            )
            target = db.execute(
                """
                SELECT name FROM menu_categories
                WHERE name = ? COLLATE NOCASE AND id != ?
                """,
                (requested_target, category_id),
            ).fetchone()
            if target is None:
                flash("Choose another existing category.", "error")
                return redirect(url_for("host_editor", manage_categories="1"))
            target_category = target["name"]
        elif item_action == "new":
            target_category = clean_category_name(
                request.form.get("new_category", "")
            )
            error = category_name_error(target_category)
            if error:
                flash(error, "error")
                return redirect(url_for("host_editor", manage_categories="1"))
            existing = db.execute(
                "SELECT name FROM menu_categories WHERE name = ? COLLATE NOCASE",
                (target_category,),
            ).fetchone()
            if existing:
                flash(
                    f"Category {existing['name']} already exists; select it instead.",
                    "error",
                )
                return redirect(url_for("host_editor", manage_categories="1"))
            next_category_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menu_categories"
            ).fetchone()[0]
            db.execute(
                "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
                (target_category, next_category_order),
            )
        elif item_action == "unassigned":
            target_category = UNASSIGNED_CATEGORY

        if item_action == "delete":
            db.execute(
                "DELETE FROM menu_items WHERE category = ? COLLATE NOCASE",
                (category["name"],),
            )
        else:
            next_item_order = db.execute(
                """
                SELECT COALESCE(MAX(sort_order), 0)
                FROM menu_items WHERE category = ? COLLATE NOCASE
                """,
                (target_category,),
            ).fetchone()[0]
            db.executemany(
                """
                UPDATE menu_items
                SET category = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [
                    (target_category, next_item_order + index, item["id"])
                    for index, item in enumerate(items, start=1)
                ],
            )
        db.execute("DELETE FROM menu_categories WHERE id = ?", (category_id,))
        normalize_category_positions(db)
        db.commit()
        if item_action == "delete":
            for item in items:
                delete_uploaded_image(item["image"])

        item_count = len(items)
        if not item_count:
            message = f"Removed category {category['name']}."
        elif item_action == "delete":
            noun = "item" if item_count == 1 else "items"
            message = f"Removed category {category['name']} and deleted {item_count} {noun}."
        elif item_action == "unassigned":
            message = f"Removed category {category['name']}; its items are now hidden in {UNASSIGNED_CATEGORY}."
        else:
            message = f"Removed category {category['name']} and moved its items to {target_category}."
        flash(message, "success")
        return redirect(url_for("host_editor", manage_categories="1"))

    @app.post("/host/category/<int:category_id>/move/<direction>")
    @host_required
    def move_category(category_id: int, direction: str):
        if direction not in {"up", "down"}:
            abort(404)
        db = get_db()
        category = db.execute(
            "SELECT id, name FROM menu_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if category is None:
            abort(404)

        normalize_category_positions(db)
        current = db.execute(
            "SELECT sort_order FROM menu_categories WHERE id = ?",
            (category_id,),
        ).fetchone()[0]
        neighbor_order = current - 1 if direction == "up" else current + 1
        neighbor = db.execute(
            "SELECT id FROM menu_categories WHERE sort_order = ?",
            (neighbor_order,),
        ).fetchone()
        if neighbor is not None:
            db.execute(
                "UPDATE menu_categories SET sort_order = -1 WHERE id = ?",
                (category_id,),
            )
            db.execute(
                "UPDATE menu_categories SET sort_order = ? WHERE id = ?",
                (current, neighbor["id"]),
            )
            db.execute(
                "UPDATE menu_categories SET sort_order = ? WHERE id = ?",
                (neighbor_order, category_id),
            )
            db.commit()
            flash(f"Moved category {category['name']} {direction}.", "success")

        return redirect(url_for("host_editor", manage_categories="1"))

    @app.post("/host/item/<int:item_id>/toggle")
    @host_required
    def toggle_item(item_id: int):
        db = get_db()
        item = db.execute("SELECT name, available FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        new_value = int(not item["available"])
        db.execute(
            "UPDATE menu_items SET available = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_value, item_id),
        )
        db.commit()
        flash(f"{item['name']} is now {'available' if new_value else 'out'}.", "success")
        return redirect(request.referrer or url_for("host_editor"))

    @app.post("/host/item/<int:item_id>/move/<direction>")
    @host_required
    def move_item(item_id: int, direction: str):
        if direction not in {"up", "down"}:
            abort(404)
        db = get_db()
        item = db.execute(
            "SELECT id, name, category FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            abort(404)

        normalize_category_order(db, item["category"])
        current = db.execute(
            "SELECT sort_order FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()[0]
        neighbor_order = current - 1 if direction == "up" else current + 1
        neighbor = db.execute(
            "SELECT id FROM menu_items WHERE category = ? AND sort_order = ?",
            (item["category"], neighbor_order),
        ).fetchone()
        if neighbor is not None:
            db.execute(
                "UPDATE menu_items SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (-1, item_id),
            )
            db.execute(
                "UPDATE menu_items SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (current, neighbor["id"]),
            )
            db.execute(
                "UPDATE menu_items SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (neighbor_order, item_id),
            )
            db.commit()
            flash(f"Moved {item['name']} {direction}.", "success")

        return_to = request.form.get("return_to", "")
        if not return_to.startswith("/host"):
            return_to = url_for("host_editor", category=item["category"])
        return redirect(return_to)

    @app.post("/host/item/<int:item_id>/delete")
    @host_required
    def delete_item(item_id: int):
        db = get_db()
        item = db.execute(
            "SELECT name, image, category FROM menu_items WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            abort(404)
        db.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
        normalize_category_order(db, item["category"])
        db.commit()
        delete_uploaded_image(item["image"])
        flash(f"Deleted {item['name']}.", "success")
        return redirect(url_for("host_editor"))

    @app.get("/host/template.csv")
    @host_required
    def csv_template():
        content = io.StringIO()
        writer = csv.writer(content)
        writer.writerow(MENU_EXPORT_COLUMNS)
        writer.writerow(("Espresso Martini", "Vodka, espresso, coffee liqueur.", "Cocktails", "yes", "", "images/espresso-martini.jpg", "1", "1"))
        writer.writerow(("Sparkling Water", "Cold and fizzy.", "Booze, Beer & Wine", "yes", "https://example.com/water.jpg", "", "2", "1"))
        payload = io.BytesIO(content.getvalue().encode("utf-8"))
        return send_file(payload, mimetype="text/csv", as_attachment=True, download_name="menu-template.csv")

    @app.get("/host/export.zip")
    @host_required
    def export_menu():
        payload = build_menu_export()
        filename = f"party-menu-export-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        return send_file(
            payload,
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
        )

    @app.post("/host/bulk-import")
    @host_required
    def bulk_import():
        upload = request.files.get("bulk_file")
        if not upload or not upload.filename:
            flash("Choose a CSV or ZIP file first.", "error")
            return redirect(url_for("host_editor"))
        replace = request.form.get("import_mode") == "replace"
        try:
            imported, skipped = import_bulk_file(
                upload.filename,
                upload.read(),
                replace=replace,
            )
        except (ValueError, csv.Error, zipfile.BadZipFile, UnicodeDecodeError) as error:
            flash(f"Import failed: {error}", "error")
            return redirect(url_for("host_editor"))
        if replace:
            flash(f"Restored the menu from the archive with {imported} item(s).", "success")
        else:
            flash(f"Imported {imported} item(s). Skipped {skipped} invalid row(s).", "success")
        return redirect(url_for("host_editor"))


def build_menu_export() -> io.BytesIO:
    db = get_db()
    categories = db.execute(
        "SELECT name, sort_order FROM menu_categories ORDER BY sort_order, id"
    ).fetchall()
    category_orders = {
        row["name"].casefold(): row["sort_order"] for row in categories
    }
    items = db.execute(
        f"SELECT * FROM menu_items ORDER BY {category_order_sql()}, sort_order, id"
    ).fetchall()

    menu_content = io.StringIO(newline="")
    menu_writer = csv.DictWriter(menu_content, fieldnames=MENU_EXPORT_COLUMNS)
    menu_writer.writeheader()
    archived_images: dict[str, str] = {}
    image_payloads: list[tuple[str, bytes]] = []

    for item in items:
        image_url = ""
        image_filename = ""
        image = item["image"]
        if image.startswith(("https://", "http://")):
            image_url = image
        elif image:
            source = None
            if image.startswith("/uploads/"):
                source = Path(current_app.config["UPLOAD_DIR"]) / Path(image).name
            elif image.startswith("/static/"):
                source = BASE_DIR / image.lstrip("/")
            if source is not None and source.is_file():
                image_filename = archived_images.get(image, "")
                if not image_filename:
                    safe_name = secure_filename(source.name) or f"item-{item['id']}.jpg"
                    image_filename = f"images/{item['id']}-{safe_name}"
                    archived_images[image] = image_filename
                    image_payloads.append((image_filename, source.read_bytes()))

        menu_writer.writerow(
            {
                "name": item["name"],
                "description": item["description"],
                "category": item["category"],
                "available": "yes" if item["available"] else "no",
                "image_url": image_url,
                "image_filename": image_filename,
                "category_order": category_orders.get(item["category"].casefold(), ""),
                "sort_order": item["sort_order"],
            }
        )

    category_content = io.StringIO(newline="")
    category_writer = csv.writer(category_content)
    category_writer.writerow(("name", "sort_order"))
    for category in categories:
        category_writer.writerow((category["name"], category["sort_order"]))

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("menu.csv", menu_content.getvalue().encode("utf-8"))
        archive.writestr("categories.csv", category_content.getvalue().encode("utf-8"))
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "party-menu-export",
                    "version": EXPORT_FORMAT_VERSION,
                    "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                indent=2,
            ).encode("utf-8"),
        )
        for filename, image_payload in image_payloads:
            archive.writestr(filename, image_payload)
    payload.seek(0)
    return payload


def import_bulk_file(
    filename: str, payload: bytes, *, replace: bool = False
) -> tuple[int, int]:
    csv_payload, image_files, categories_payload = unpack_bulk_file(filename, payload)
    if replace:
        return replace_menu_from_archive(csv_payload, image_files, categories_payload)
    return append_bulk_items(csv_payload, image_files)


def unpack_bulk_file(
    filename: str, payload: bytes
) -> tuple[bytes, dict[str, tuple[str, bytes]], bytes | None]:
    extension = Path(secure_filename(filename)).suffix.lower()
    image_files: dict[str, tuple[str, bytes]] = {}
    categories_payload = None
    if extension == ".csv":
        csv_payload = payload
    elif extension == ".zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if sum(member.file_size for member in members) > 200 * 1024 * 1024:
                raise ValueError("The extracted ZIP may not exceed 200 MB.")
            menu_members = [
                member
                for member in members
                if PurePosixPath(member.filename).name.casefold() == "menu.csv"
            ]
            csv_members = [
                member
                for member in members
                if PurePosixPath(member.filename).suffix.lower() == ".csv"
                and PurePosixPath(member.filename).name.casefold() != "categories.csv"
            ]
            if not menu_members and not csv_members:
                raise ValueError("The ZIP must contain a CSV file.")
            preferred = menu_members[0] if menu_members else csv_members[0]
            if preferred.file_size > 5 * 1024 * 1024:
                raise ValueError("The CSV inside the ZIP may not exceed 5 MB.")
            csv_payload = archive.read(preferred)
            categories_member = next(
                (
                    member
                    for member in members
                    if PurePosixPath(member.filename).name.casefold()
                    == "categories.csv"
                ),
                None,
            )
            if categories_member is not None:
                if categories_member.file_size > 1024 * 1024:
                    raise ValueError("categories.csv may not exceed 1 MB.")
                categories_payload = archive.read(categories_member)
            for member in members:
                path = PurePosixPath(member.filename)
                if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS or member.file_size > MAX_IMAGE_BYTES:
                    continue
                image_payload = archive.read(member)
                normalized = str(path).lstrip("./")
                image_files[normalized.casefold()] = (path.name, image_payload)
                image_files.setdefault(path.name.casefold(), (path.name, image_payload))
    else:
        raise ValueError("Only .csv and .zip files are supported.")
    return csv_payload, image_files, categories_payload


def read_menu_rows(csv_payload: bytes) -> list[dict[str, str]]:
    text_stream = io.StringIO(csv_payload.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)
    fields = {(field or "").strip().casefold() for field in reader.fieldnames or []}
    if "name" not in fields:
        raise ValueError("The CSV must include a name column.")
    return [
        {
            (key or "").strip().casefold(): (value or "").strip()
            for key, value in raw_row.items()
        }
        for raw_row in reader
    ]


def append_bulk_items(
    csv_payload: bytes, image_files: dict[str, tuple[str, bytes]]
) -> tuple[int, int]:
    rows = read_menu_rows(csv_payload)

    db = get_db()
    next_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM menu_items").fetchone()[0]
    imported = 0
    skipped = 0
    for row in rows:
        name = " ".join(row.get("name", "").split())
        category = canonical_category(row.get("category", ""))
        if not name or not category:
            skipped += 1
            continue
        image = clean_image_reference(row.get("image_url"))
        image_filename = row.get("image_filename", "").lstrip("./")
        if image_filename:
            match = image_files.get(image_filename.casefold()) or image_files.get(PurePosixPath(image_filename).name.casefold())
            if match:
                image = save_image_bytes(match[0], match[1])
        next_order += 1
        db.execute(
            """
            INSERT INTO menu_items
                (name, description, category, image, available, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                row.get("description", ""),
                category,
                image,
                parse_available(row.get("available")),
                next_order,
            ),
        )
        imported += 1
    db.commit()
    return imported, skipped


def replace_menu_from_archive(
    csv_payload: bytes,
    image_files: dict[str, tuple[str, bytes]],
    categories_payload: bytes | None,
) -> tuple[int, int]:
    rows = read_menu_rows(csv_payload)
    category_specs = read_export_categories(categories_payload, rows)
    category_names = {name.casefold(): name for name, _sort_order in category_specs}
    prepared_items = []
    per_category_order: dict[str, int] = {}

    for row_number, row in enumerate(rows, start=2):
        name = " ".join(row.get("name", "").split())
        raw_category = clean_category_name(row.get("category", ""))
        if not name or not raw_category:
            raise ValueError(f"Invalid item on menu.csv row {row_number}.")
        if raw_category.casefold() == UNASSIGNED_CATEGORY.casefold():
            category = UNASSIGNED_CATEGORY
        else:
            category = category_names.get(raw_category.casefold())
            if category is None:
                raise ValueError(
                    f"Unknown category {raw_category} on menu.csv row {row_number}."
                )

        image = clean_image_reference(row.get("image_url"))
        image_match = None
        image_filename = row.get("image_filename", "").lstrip("./")
        if image_filename:
            image_match = image_files.get(image_filename.casefold()) or image_files.get(
                PurePosixPath(image_filename).name.casefold()
            )
            if image_match is None:
                raise ValueError(
                    f"Missing image {image_filename} referenced on menu.csv row {row_number}."
                )

        category_key = category.casefold()
        per_category_order[category_key] = per_category_order.get(category_key, 0) + 1
        try:
            sort_order = int(row.get("sort_order") or per_category_order[category_key])
        except ValueError as error:
            raise ValueError(
                f"Invalid sort_order on menu.csv row {row_number}."
            ) from error
        prepared_items.append(
            {
                "name": name,
                "description": row.get("description", ""),
                "category": category,
                "available": parse_available(row.get("available")),
                "sort_order": sort_order,
                "image": image,
                "image_match": image_match,
            }
        )

    db = get_db()
    old_uploaded_images = [
        row["image"]
        for row in db.execute(
            "SELECT DISTINCT image FROM menu_items WHERE image LIKE '/uploads/%'"
        ).fetchall()
    ]
    saved_images = []
    try:
        for item in prepared_items:
            if item["image_match"]:
                item["image"] = save_image_bytes(*item["image_match"])
                saved_images.append(item["image"])

        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM menu_items")
        db.execute("DELETE FROM menu_categories")
        db.executemany(
            "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
            category_specs,
        )
        db.executemany(
            """
            INSERT INTO menu_items
                (name, description, category, image, available, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["name"],
                    item["description"],
                    item["category"],
                    item["image"],
                    item["available"],
                    item["sort_order"],
                )
                for item in prepared_items
            ],
        )
        db.execute(
            """
            INSERT INTO app_meta (key, value) VALUES ('categories_initialized', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        db.commit()
    except Exception:
        db.rollback()
        for image in saved_images:
            (Path(current_app.config["UPLOAD_DIR"]) / Path(image).name).unlink(
                missing_ok=True
            )
        raise

    for image in old_uploaded_images:
        delete_uploaded_image(image)
    return len(prepared_items), 0


def read_export_categories(
    categories_payload: bytes | None, rows: list[dict[str, str]]
) -> list[tuple[str, int]]:
    raw_categories = []
    if categories_payload is not None:
        reader = csv.DictReader(
            io.StringIO(categories_payload.decode("utf-8-sig"))
        )
        fields = {
            (field or "").strip().casefold() for field in reader.fieldnames or []
        }
        if "name" not in fields:
            raise ValueError("categories.csv must include a name column.")
        for index, raw_row in enumerate(reader, start=1):
            row = {
                (key or "").strip().casefold(): (value or "").strip()
                for key, value in raw_row.items()
            }
            raw_categories.append((row.get("name", ""), row.get("sort_order", ""), index))
    else:
        seen = set()
        for index, row in enumerate(rows, start=1):
            name = clean_category_name(row.get("category", ""))
            if not name or name.casefold() == UNASSIGNED_CATEGORY.casefold():
                continue
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            raw_categories.append((name, row.get("category_order", ""), index))

    categories = []
    seen = set()
    for raw_name, raw_order, fallback_order in raw_categories:
        name = clean_category_name(raw_name)
        error = category_name_error(name)
        if error:
            raise ValueError(error)
        if name.casefold() in seen:
            raise ValueError(f"Duplicate category {name} in the archive.")
        seen.add(name.casefold())
        try:
            sort_order = int(raw_order or fallback_order)
        except ValueError as error:
            raise ValueError(f"Invalid sort order for category {name}.") from error
        categories.append((name, sort_order))
    categories.sort(key=lambda category: category[1])
    return categories


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
