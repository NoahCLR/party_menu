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
    for sort_order, category in enumerate(DEFAULT_CATEGORIES, start=1):
        db.execute(
            """
            INSERT INTO menu_categories (name, sort_order)
            VALUES (?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (category, sort_order),
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
        WHERE menu_categories.id IS NULL AND TRIM(menu_items.category) != ''
        ORDER BY menu_items.category COLLATE NOCASE
        """
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
    return None


def canonical_category(value: str) -> str | None:
    display_name = clean_category_name(value)
    if not display_name:
        return None
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
            f"SELECT * FROM menu_items ORDER BY {category_order_sql()}, sort_order, id"
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
        if not item["available"]:
            flash(f"{item['name']} is currently out.", "error")
            return redirect(url_for("menu"))

        if request.method == "GET":
            return render_template("order.html", item=item, guest_name="", note="")

        guest_name = " ".join(request.form.get("guest_name", "").strip().split())
        note = request.form.get("note", "").strip()
        if not guest_name:
            flash("Enter your name before sending the order.", "error")
            return render_template(
                "order.html", item=item, guest_name=guest_name, note=note
            ), 400
        if len(guest_name) > 80:
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
        return redirect(url_for("menu"))

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
        selected_category = request.args.get("category", "All items")
        selected_status = request.args.get("status", "all")
        conditions = []
        values = []
        if selected_category in categories:
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
        counts = {
            "all": len(all_rows),
            "available": sum(row["available"] for row in all_rows),
            "out": sum(not row["available"] for row in all_rows),
            **{category: sum(row["category"] == category for row in all_rows) for category in categories},
        }
        order_rows = db.execute(
            f"SELECT id, category FROM menu_items ORDER BY {category_order_sql()}, sort_order, id"
        ).fetchall()
        category_ids = {category: [] for category in categories}
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
            category_rows=category_rows,
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
        writer.writerow(("name", "description", "category", "available", "image_url", "image_filename"))
        writer.writerow(("Espresso Martini", "Vodka, espresso, coffee liqueur.", "Cocktails", "yes", "", "images/espresso-martini.jpg"))
        writer.writerow(("Sparkling Water", "Cold and fizzy.", "Booze, Beer & Wine", "yes", "https://example.com/water.jpg", ""))
        payload = io.BytesIO(content.getvalue().encode("utf-8"))
        return send_file(payload, mimetype="text/csv", as_attachment=True, download_name="menu-template.csv")

    @app.post("/host/bulk-import")
    @host_required
    def bulk_import():
        upload = request.files.get("bulk_file")
        if not upload or not upload.filename:
            flash("Choose a CSV or ZIP file first.", "error")
            return redirect(url_for("host_editor"))
        try:
            imported, skipped = import_bulk_file(upload.filename, upload.read())
        except (ValueError, csv.Error, zipfile.BadZipFile, UnicodeDecodeError) as error:
            flash(f"Import failed: {error}", "error")
            return redirect(url_for("host_editor"))
        flash(f"Imported {imported} item(s). Skipped {skipped} invalid row(s).", "success")
        return redirect(url_for("host_editor"))


def import_bulk_file(filename: str, payload: bytes) -> tuple[int, int]:
    extension = Path(secure_filename(filename)).suffix.lower()
    image_files: dict[str, tuple[str, bytes]] = {}
    if extension == ".csv":
        csv_payload = payload
    elif extension == ".zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            csv_members = [member for member in members if PurePosixPath(member.filename).suffix.lower() == ".csv"]
            if not csv_members:
                raise ValueError("The ZIP must contain a CSV file.")
            preferred = next((member for member in csv_members if PurePosixPath(member.filename).name.casefold() == "menu.csv"), csv_members[0])
            if preferred.file_size > 5 * 1024 * 1024:
                raise ValueError("The CSV inside the ZIP may not exceed 5 MB.")
            csv_payload = archive.read(preferred)
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

    text_stream = io.StringIO(csv_payload.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)
    if not reader.fieldnames or "name" not in {(field or "").strip().casefold() for field in reader.fieldnames}:
        raise ValueError("The CSV must include a name column.")

    db = get_db()
    next_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM menu_items").fetchone()[0]
    imported = 0
    skipped = 0
    for raw_row in reader:
        row = {(key or "").strip().casefold(): (value or "").strip() for key, value in raw_row.items()}
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


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
