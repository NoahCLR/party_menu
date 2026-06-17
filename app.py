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
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
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
from PIL import Image, ImageOps, UnidentifiedImageError
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
MAX_IMAGE_DIMENSION = 1600
MAX_IMAGE_PIXELS = 40_000_000
WEBP_QUALITY = 84
CATALOG_VERSION = "4"
PUSHOVER_MESSAGES_URL = "https://api.pushover.net/1/messages.json"
UNASSIGNED_CATEGORY = "Unassigned"
UNASSIGNED_RECIPIENT = "Unassigned"
GUEST_NAME_COOKIE = "party_guest_name"
GUEST_NAME_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
MAX_BASKET_DISTINCT_ITEMS = 25
MAX_BASKET_QUANTITY = 20
MAX_BASKET_TOTAL_ITEMS = 50
MAX_PUSHOVER_MESSAGE_LENGTH = 1024
MAX_RECIPE_INGREDIENTS = 20
MAX_RECIPE_INGREDIENT_NAME_LENGTH = 80
MAX_RECIPE_ML = Decimal("10000")
MAX_RECIPE_ABV = Decimal("100")
ALCOHOL_GRAMS_PER_ML = Decimal("0.789")
STANDARD_DRINK_GRAMS = Decimal("10")
EXPORT_FORMAT_VERSION = 2
MENU_EXPORT_COLUMNS = (
    "name",
    "description",
    "category",
    "available",
    "image_url",
    "image_filename",
    "image_focus_x",
    "image_focus_y",
    "category_order",
    "sort_order",
    "recipe",
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

SEED_SINGLE_SERVE_RECIPES = (
    ("Vodka", "Hard Drinks", ({"name": "Vodka", "ml": "40", "abv": "40"},)),
    ("Whiskey", "Hard Drinks", ({"name": "Whiskey", "ml": "40", "abv": "40"},)),
    ("Rum", "Hard Drinks", ({"name": "Rum", "ml": "40", "abv": "40"},)),
    ("Gin", "Hard Drinks", ({"name": "Gin", "ml": "40", "abv": "40"},)),
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
        g.db.execute("PRAGMA foreign_keys = ON")
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
            recipe TEXT NOT NULL DEFAULT '[]',
            image_focus_x REAL NOT NULL DEFAULT 50,
            image_focus_y REAL NOT NULL DEFAULT 50,
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
        CREATE TABLE IF NOT EXISTS guest_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_name TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'single',
            status TEXT NOT NULL DEFAULT 'new',
            item_count INTEGER NOT NULL DEFAULT 0,
            total_alcohol_ml REAL NOT NULL DEFAULT 0,
            total_alcohol_grams REAL NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            CHECK (source IN ('single', 'basket')),
            CHECK (status IN ('new', 'completed'))
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_item_id INTEGER,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            recipient_name TEXT NOT NULL DEFAULT '',
            recipe TEXT NOT NULL DEFAULT '[]',
            alcohol_ml REAL NOT NULL DEFAULT 0,
            alcohol_grams REAL NOT NULL DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_orders_status_submitted
            ON orders(status, submitted_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_order_items_order
            ON order_items(order_id);
        """
    )
    menu_item_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(menu_items)").fetchall()
    }
    if "recipe" not in menu_item_columns:
        db.execute(
            "ALTER TABLE menu_items ADD COLUMN recipe TEXT NOT NULL DEFAULT '[]'"
        )
    if "image_focus_x" not in menu_item_columns:
        db.execute(
            "ALTER TABLE menu_items ADD COLUMN image_focus_x REAL NOT NULL DEFAULT 50"
        )
    if "image_focus_y" not in menu_item_columns:
        db.execute(
            "ALTER TABLE menu_items ADD COLUMN image_focus_y REAL NOT NULL DEFAULT 50"
        )
    order_item_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(order_items)").fetchall()
    }
    if "recipient_name" not in order_item_columns:
        db.execute(
            "ALTER TABLE order_items ADD COLUMN recipient_name TEXT NOT NULL DEFAULT ''"
        )
    if "completed_at" not in order_item_columns:
        db.execute("ALTER TABLE order_items ADD COLUMN completed_at TEXT")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_items_recipient ON order_items(recipient_name)"
    )
    db.execute("BEGIN IMMEDIATE")
    if "recipient_name" not in order_item_columns:
        db.execute(
            """
            UPDATE order_items
            SET recipient_name = (
                SELECT guest_name FROM orders WHERE orders.id = order_items.order_id
            )
            WHERE TRIM(recipient_name) = ''
            """
        )
    if "completed_at" not in order_item_columns:
        db.execute(
            """
            UPDATE order_items
            SET completed_at = (
                SELECT completed_at FROM orders WHERE orders.id = order_items.order_id
            )
            WHERE completed_at IS NULL
                AND order_id IN (
                    SELECT id FROM orders WHERE status = 'completed'
                )
            """
        )
    for row in db.execute("SELECT id, guest_name FROM orders").fetchall():
        normalized_name = normalize_stored_guest_name(row["guest_name"])
        if normalized_name != row["guest_name"]:
            db.execute(
                "UPDATE orders SET guest_name = ? WHERE id = ?",
                (normalized_name, row["id"]),
            )
    for row in db.execute("SELECT id, recipient_name FROM order_items").fetchall():
        normalized_name = normalize_stored_guest_name(
            row["recipient_name"], allow_empty=True
        )
        if normalized_name != row["recipient_name"]:
            db.execute(
                "UPDATE order_items SET recipient_name = ? WHERE id = ?",
                (normalized_name, row["id"]),
            )
    db.execute(
        """
        INSERT OR IGNORE INTO guest_names (name)
        SELECT DISTINCT guest_name
        FROM orders
        WHERE TRIM(guest_name) != '' AND guest_name != ? COLLATE NOCASE
        """,
        (UNASSIGNED_RECIPIENT,),
    )
    db.execute(
        """
        INSERT OR IGNORE INTO guest_names (name)
        SELECT DISTINCT recipient_name
        FROM order_items
        WHERE TRIM(recipient_name) != ''
            AND recipient_name != ? COLLATE NOCASE
        """,
        (UNASSIGNED_RECIPIENT,),
    )
    for row in db.execute("SELECT name FROM guest_names").fetchall():
        canonical_name = row["name"]
        db.execute(
            """
            UPDATE orders
            SET guest_name = ?
            WHERE guest_name = ? COLLATE NOCASE
            """,
            (canonical_name, canonical_name),
        )
        db.execute(
            """
            UPDATE order_items
            SET recipient_name = ?
            WHERE recipient_name = ? COLLATE NOCASE
            """,
            (canonical_name, canonical_name),
        )
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
    if catalog_version < 4:
        db.executemany(
            """
            UPDATE menu_items
            SET recipe = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ? AND category = ?
                AND (recipe IS NULL OR TRIM(recipe) = '' OR TRIM(recipe) = '[]')
            """,
            [
                (recipe_json(list(recipe)), name, category)
                for name, category, recipe in SEED_SINGLE_SERVE_RECIPES
            ],
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


def collapse_guest_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def clean_guest_name(value: str | None) -> str:
    return collapse_guest_name(value)[:80]


def is_reserved_guest_name(value: str | None) -> bool:
    return clean_guest_name(value).casefold() == UNASSIGNED_RECIPIENT.casefold()


def normalize_guest_name_input(
    value: object,
    *,
    allow_empty: bool = False,
    type_message: str = "Names must be text.",
    empty_message: str = "Enter a name.",
    length_message: str = "Names may not exceed 80 characters.",
) -> str:
    if not isinstance(value, str):
        raise ValueError(type_message)
    submitted = collapse_guest_name(value)
    if not submitted and not allow_empty:
        raise ValueError(empty_message)
    if len(submitted) > 80:
        raise ValueError(length_message)
    if is_reserved_guest_name(submitted):
        raise ValueError("Unassigned is reserved for the host.")
    return submitted


def normalize_orderer_name(value: object) -> str:
    return normalize_guest_name_input(
        value,
        type_message="Your name must be text.",
        empty_message="Enter your name before sending the order.",
        length_message="Your name may not exceed 80 characters.",
    )


def normalize_recipient_name(value: object) -> str:
    return normalize_guest_name_input(
        value,
        allow_empty=True,
        type_message="Drink names must be text.",
        length_message="Drink names may not exceed 80 characters.",
    )


def normalize_stored_guest_name(value: str | None, *, allow_empty: bool = False) -> str:
    name = clean_guest_name(value)
    if not name or is_reserved_guest_name(name):
        return "" if allow_empty else "Guest"
    return name


def canonical_guest_name(name: str) -> str:
    if not name or is_reserved_guest_name(name):
        return name
    existing = get_db().execute(
        "SELECT name FROM guest_names WHERE name = ? COLLATE NOCASE",
        (name,),
    ).fetchone()
    return existing["name"] if existing else name


def guest_name_label(value: str | None) -> str:
    name = clean_guest_name(value)
    return name if name else UNASSIGNED_RECIPIENT


def remember_guest_names(names: list[str]) -> None:
    db = get_db()
    seen = set()
    for raw_name in names:
        name = clean_guest_name(raw_name)
        key = name.casefold()
        if not name or is_reserved_guest_name(name) or key in seen:
            continue
        seen.add(key)
        db.execute("INSERT OR IGNORE INTO guest_names (name) VALUES (?)", (name,))
        db.execute(
            """
            UPDATE guest_names
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE name = ? COLLATE NOCASE
            """,
            (name,),
        )


def load_guest_name_options(limit: int | None = None) -> list[str]:
    query = """
        SELECT name
        FROM guest_names
        WHERE name != ? COLLATE NOCASE
        ORDER BY last_seen_at DESC, name COLLATE NOCASE
        """
    params: list[object] = [UNASSIGNED_RECIPIENT]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    rows = get_db().execute(query, params).fetchall()
    return [row["name"] for row in rows]


def normalize_recipe(entries: object) -> list[dict[str, str]]:
    if entries in (None, ""):
        return []
    if not isinstance(entries, list):
        raise ValueError("Recipe must be a list of ingredients.")
    if len(entries) > MAX_RECIPE_INGREDIENTS:
        raise ValueError(
            f"Recipes may contain at most {MAX_RECIPE_INGREDIENTS} ingredients."
        )

    recipe = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each recipe ingredient must include a name and ml value.")
        name = " ".join(str(entry.get("name", "")).strip().split())
        raw_ml = str(entry.get("ml", "")).strip()
        raw_abv = str(entry.get("abv", "")).strip().removesuffix("%").strip()
        if not name and not raw_ml and not raw_abv:
            continue
        if not name:
            raise ValueError("Every recipe amount needs an ingredient name.")
        if len(name) > MAX_RECIPE_INGREDIENT_NAME_LENGTH:
            raise ValueError(
                "Recipe ingredient names may not exceed "
                f"{MAX_RECIPE_INGREDIENT_NAME_LENGTH} characters."
            )

        ml = ""
        if raw_ml:
            try:
                amount = Decimal(raw_ml)
            except InvalidOperation as error:
                raise ValueError(f"Invalid ml amount for {name}.") from error
            if not amount.is_finite() or amount <= 0 or amount > MAX_RECIPE_ML:
                raise ValueError(
                    f"The ml amount for {name} must be between 0 and {MAX_RECIPE_ML}."
                )
            if amount.as_tuple().exponent < -2:
                raise ValueError(
                    f"The ml amount for {name} may have two decimals at most."
                )
            ml = format(amount.normalize(), "f")

        abv = ""
        if raw_abv:
            if not raw_ml:
                raise ValueError(f"The ABV for {name} needs a ml amount.")
            try:
                percentage = Decimal(raw_abv)
            except InvalidOperation as error:
                raise ValueError(f"Invalid ABV percentage for {name}.") from error
            if not percentage.is_finite() or percentage < 0 or percentage > MAX_RECIPE_ABV:
                raise ValueError(
                    f"The ABV for {name} must be between 0 and {MAX_RECIPE_ABV}."
                )
            if percentage.as_tuple().exponent < -2:
                raise ValueError(
                    f"The ABV for {name} may have two decimals at most."
                )
            abv = format(percentage.normalize(), "f")

        ingredient = {"name": name, "ml": ml}
        if abv:
            ingredient["abv"] = abv
        recipe.append(ingredient)
    return recipe


def parse_recipe_json(value: str | None) -> list[dict[str, str]]:
    if not value:
        return []
    try:
        entries = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("Recipe must be valid JSON.") from error
    return normalize_recipe(entries)


def parse_recipe_form() -> list[dict[str, str]]:
    names = request.form.getlist("recipe_name")
    amounts = request.form.getlist("recipe_ml")
    abvs = request.form.getlist("recipe_abv")
    row_count = max(len(names), len(amounts), len(abvs))
    return normalize_recipe(
        [
            {
                "name": names[index] if index < len(names) else "",
                "ml": amounts[index] if index < len(amounts) else "",
                "abv": abvs[index] if index < len(abvs) else "",
            }
            for index in range(row_count)
        ]
    )


def recipe_json(recipe: list[dict[str, str]]) -> str:
    return json.dumps(recipe, ensure_ascii=True, separators=(",", ":"))


def parse_focus(value: str | float | int | None, default: float = 50) -> float:
    try:
        focus = float(value)
    except (TypeError, ValueError):
        return default
    return min(100, max(0, focus))


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

    try:
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with Image.open(io.BytesIO(payload)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions are too large.")
            source.seek(0)
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS
            )
            if "A" in image.getbands():
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
            encoded = io.BytesIO()
            image.save(
                encoded,
                format="WEBP",
                quality=WEBP_QUALITY,
                method=6,
            )
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ValueError("The uploaded file is not a valid supported image.") from error

    stem = secure_filename(Path(original).stem)[:60] or "menu-item"
    stored_name = f"{stem}-{uuid.uuid4().hex[:10]}.webp"
    destination = Path(current_app_upload_dir()) / stored_name
    destination.write_bytes(encoded.getvalue())
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


def send_pushover_message(title: str, message: str) -> None:
    token = current_app.config["PUSHOVER_API_TOKEN"]
    user_key = current_app.config["PUSHOVER_USER_KEY"]
    if not token or not user_key:
        raise PushoverError("Pushover credentials are not configured.")

    payload = urlencode(
        {
            "token": token,
            "user": user_key,
            "title": title,
            "message": message,
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


def format_recipe_section(items: list[dict]) -> str:
    recipes = []
    for item in items:
        recipe = item.get("recipe") or []
        if not recipe:
            continue
        lines = [item["name"]]
        lines.extend(format_recipe_ingredient_line(ingredient) for ingredient in recipe)
        recipes.append("\n".join(lines))
    return "\n\n".join(recipes)


def format_recipe_ingredient_line(ingredient: dict[str, str]) -> str:
    amount = f"{ingredient['ml']} ml " if ingredient.get("ml") else ""
    abv = f" ({ingredient['abv']}% ABV)" if ingredient.get("abv") else ""
    return f"- {amount}{ingredient['name']}{abv}"


def unique_guest_name_labels(names: list[str | None]) -> list[str]:
    labels = []
    seen = set()
    for raw_name in names:
        name = guest_name_label(raw_name)
        key = name.casefold()
        if key in seen:
            continue
        labels.append(name)
        seen.add(key)
    return labels


def basket_recipient_names(items: list[dict], guest_name: str) -> list[str]:
    names = []
    for item in items:
        quantity = int(item.get("quantity", 1))
        recipients = item.get("recipients") or [guest_name] * quantity
        names.extend(recipient or guest_name for recipient in recipients)
    return unique_guest_name_labels(names or [guest_name])


def format_guest_name_list(names: list[str]) -> str:
    return ", ".join(names)


def format_order_title(guest_name: str, recipient_names: list[str]) -> str:
    recipient_summary = format_guest_name_list(recipient_names)
    if not recipient_summary or recipient_summary.casefold() == guest_name.casefold():
        return f"Order from {guest_name}"
    return f"Order from {guest_name} for {recipient_summary}"


def format_pushover_order_title(recipient_names: list[str]) -> str:
    recipient_summary = format_guest_name_list(recipient_names)
    return f"Order for {recipient_summary}" if recipient_summary else "New order"


def format_basket_item_line(item: dict, guest_name: str) -> str:
    recipient_summary = format_guest_name_list(
        basket_recipient_names([item], guest_name)
    )
    recipient_suffix = f" for {recipient_summary}" if recipient_summary else ""
    return f"{item['quantity']}x {item['name']}{recipient_suffix}"


def format_single_order_message(
    item_name: str,
    category: str,
    note: str,
    recipe: list[dict[str, str]],
) -> str:
    message = f"Item: {item_name}\nCategory: {category}"
    if note:
        message += f"\nNote: {note}"
    recipe_section = format_recipe_section(
        [{"name": item_name, "recipe": recipe}]
    )
    if recipe_section:
        message += f"\n\nRecipe:\n{recipe_section}"
    return message


def send_pushover_order(
    item_name: str,
    category: str,
    guest_name: str,
    note: str,
    recipe: list[dict[str, str]],
) -> None:
    message = format_single_order_message(item_name, category, note, recipe)
    send_pushover_message(format_pushover_order_title([guest_name]), message)


def format_basket_message(items: list[dict], guest_name: str, note: str) -> str:
    lines = ["Items:"]
    lines.extend(format_basket_item_line(item, guest_name) for item in items)
    if note:
        lines.append(f"Note: {note}")
    message = "\n".join(lines)
    recipe_section = format_recipe_section(items)
    if recipe_section:
        message += f"\n\nRecipes:\n{recipe_section}"
    return message


def send_pushover_basket_order(
    items: list[dict], guest_name: str, note: str
) -> None:
    recipient_names = basket_recipient_names(items, guest_name)
    send_pushover_message(
        format_pushover_order_title(recipient_names),
        format_basket_message(items, guest_name, note),
    )


def decimal_recipe_value(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def recipe_alcohol_totals(recipe: list[dict[str, str]]) -> tuple[Decimal, Decimal]:
    alcohol_ml = Decimal("0")
    for ingredient in recipe:
        ml = decimal_recipe_value(ingredient.get("ml"))
        abv = decimal_recipe_value(ingredient.get("abv"))
        if ml is None or abv is None or ml <= 0 or abv <= 0:
            continue
        alcohol_ml += ml * (abv / Decimal("100"))
    return alcohol_ml, alcohol_ml * ALCOHOL_GRAMS_PER_ML


def rounded_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def standard_drinks(alcohol_grams: float | Decimal) -> float:
    grams = Decimal(str(alcohol_grams))
    return rounded_float(grams / STANDARD_DRINK_GRAMS)


def create_order(
    guest_name: str,
    note: str,
    items: list[dict],
    source: str,
) -> int:
    db = get_db()
    guest_name = canonical_guest_name(normalize_orderer_name(guest_name))
    prepared_items = []
    total_quantity = 0
    total_alcohol_ml = Decimal("0")
    total_alcohol_grams = Decimal("0")

    for item in items:
        quantity = int(item.get("quantity", 1))
        raw_recipients = item.get("recipients") or [guest_name] * quantity
        if len(raw_recipients) != quantity:
            raise ValueError("Each ordered drink needs one recipient name.")
        recipients = []
        for raw_recipient in raw_recipients:
            recipient_name = normalize_recipient_name(raw_recipient)
            recipients.append(
                canonical_guest_name(recipient_name) if recipient_name else guest_name
            )

        recipe = normalize_recipe(item.get("recipe") or [])
        item_alcohol_ml, item_alcohol_grams = recipe_alcohol_totals(recipe)
        line_alcohol_ml = item_alcohol_ml * quantity
        line_alcohol_grams = item_alcohol_grams * quantity
        total_quantity += quantity
        total_alcohol_ml += line_alcohol_ml
        total_alcohol_grams += line_alcohol_grams
        recipient_counts: OrderedDict[str, int] = OrderedDict()
        for recipient_name in recipients:
            recipient_counts[recipient_name] = recipient_counts.get(recipient_name, 0) + 1
        for recipient_name, recipient_quantity in recipient_counts.items():
            prepared_items.append(
                {
                    "menu_item_id": item.get("id"),
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": recipient_quantity,
                    "recipient_name": recipient_name,
                    "recipe": recipe_json(recipe),
                    "alcohol_ml": rounded_float(item_alcohol_ml * recipient_quantity),
                    "alcohol_grams": rounded_float(
                        item_alcohol_grams * recipient_quantity
                    ),
                }
            )

    cursor = db.execute(
        """
        INSERT INTO orders
            (guest_name, note, source, item_count, total_alcohol_ml,
             total_alcohol_grams)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            guest_name,
            note,
            source,
            total_quantity,
            rounded_float(total_alcohol_ml),
            rounded_float(total_alcohol_grams),
        ),
    )
    order_id = int(cursor.lastrowid)
    db.executemany(
        """
        INSERT INTO order_items
            (order_id, menu_item_id, name, category, quantity, recipient_name, recipe,
             alcohol_ml, alcohol_grams)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                order_id,
                item["menu_item_id"],
                item["name"],
                item["category"],
                item["quantity"],
                item["recipient_name"],
                item["recipe"],
                item["alcohol_ml"],
                item["alcohol_grams"],
            )
            for item in prepared_items
        ],
    )
    remember_guest_names(
        [guest_name, *[item["recipient_name"] for item in prepared_items]]
    )
    db.commit()
    return order_id


def iso_timestamp(value: str | None) -> str | None:
    return f"{value.replace(' ', 'T')}Z" if value else None


def sync_order_status_from_items(order_id: int) -> str:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS item_rows,
            SUM(completed_at IS NULL) AS open_items
        FROM order_items
        WHERE order_id = ?
        """,
        (order_id,),
    ).fetchone()
    item_rows = row["item_rows"] or 0
    open_items = row["open_items"] or 0
    if item_rows > 0 and open_items == 0:
        db.execute(
            """
            UPDATE orders
            SET status = 'completed',
                completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (order_id,),
        )
        return "completed"
    db.execute(
        """
        UPDATE orders
        SET status = 'new', completed_at = NULL
        WHERE id = ?
        """,
        (order_id,),
    )
    return "new"


def recalculate_order_totals(order_id: int) -> bool:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS item_rows,
            COALESCE(SUM(quantity), 0) AS item_count,
            COALESCE(SUM(alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(alcohol_grams), 0) AS alcohol_grams,
            SUM(completed_at IS NULL) AS open_items
        FROM order_items
        WHERE order_id = ?
        """,
        (order_id,),
    ).fetchone()
    if not row["item_rows"]:
        db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        return False

    completed = (row["open_items"] or 0) == 0
    db.execute(
        """
        UPDATE orders
        SET item_count = ?,
            total_alcohol_ml = ?,
            total_alcohol_grams = ?,
            status = ?,
            completed_at = CASE
                WHEN ? THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                ELSE NULL
            END
        WHERE id = ?
        """,
        (
            row["item_count"] or 0,
            rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
            rounded_float(Decimal(str(row["alcohol_grams"] or 0))),
            "completed" if completed else "new",
            int(completed),
            order_id,
        ),
    )
    return True


def remove_one_order_item(item_id: int) -> tuple[int, str]:
    db = get_db()
    item = db.execute(
        """
        SELECT id, order_id, name, quantity, alcohol_ml, alcohol_grams
        FROM order_items
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()
    if item is None:
        abort(404)

    quantity = item["quantity"] or 0
    if quantity > 1:
        remaining = quantity - 1
        unit_alcohol_ml = Decimal(str(item["alcohol_ml"] or 0)) / Decimal(str(quantity))
        unit_alcohol_grams = Decimal(str(item["alcohol_grams"] or 0)) / Decimal(str(quantity))
        db.execute(
            """
            UPDATE order_items
            SET quantity = ?,
                alcohol_ml = ?,
                alcohol_grams = ?
            WHERE id = ?
            """,
            (
                remaining,
                rounded_float(unit_alcohol_ml * remaining),
                rounded_float(unit_alcohol_grams * remaining),
                item_id,
            ),
        )
    else:
        db.execute("DELETE FROM order_items WHERE id = ?", (item_id,))
    recalculate_order_totals(item["order_id"])
    return item["order_id"], item["name"]


def serialize_order(row: sqlite3.Row, items: list[sqlite3.Row]) -> dict:
    order_items = []
    for item in items:
        recipe = parse_recipe_json(item["recipe"])
        order_items.append(
            {
                "id": item["id"],
                "menu_item_id": item["menu_item_id"],
                "name": item["name"],
                "category": item["category"],
                "quantity": item["quantity"],
                "recipient_name": guest_name_label(item["recipient_name"]),
                "recipient_is_unassigned": not clean_guest_name(item["recipient_name"]),
                "completed": item["completed_at"] is not None,
                "completed_at": iso_timestamp(item["completed_at"]),
                "recipe": recipe,
                "alcohol_ml": item["alcohol_ml"],
                "alcohol_grams": item["alcohol_grams"],
                "standard_drinks": standard_drinks(item["alcohol_grams"]),
            }
        )
    recipient_names = unique_guest_name_labels(
        [item["recipient_name"] for item in order_items] or [row["guest_name"]]
    )
    recipient_summary = format_guest_name_list(recipient_names)
    return {
        "id": row["id"],
        "guest_name": row["guest_name"],
        "recipient_names": recipient_names,
        "recipient_summary": recipient_summary,
        "order_title": format_order_title(row["guest_name"], recipient_names),
        "note": row["note"],
        "source": row["source"],
        "status": row["status"],
        "item_count": row["item_count"],
        "total_alcohol_ml": row["total_alcohol_ml"],
        "total_alcohol_grams": row["total_alcohol_grams"],
        "standard_drinks": standard_drinks(row["total_alcohol_grams"]),
        "submitted_at": iso_timestamp(row["submitted_at"]),
        "completed_at": iso_timestamp(row["completed_at"]),
        "items": order_items,
    }


def load_orders(status: str = "active") -> list[dict]:
    db = get_db()
    conditions = {
        "active": "WHERE status = 'new'",
        "completed": "WHERE status = 'completed'",
        "all": "",
    }
    where = conditions.get(status, conditions["active"])
    rows = db.execute(
        f"""
        SELECT * FROM orders
        {where}
        ORDER BY
            CASE status WHEN 'new' THEN 0 ELSE 1 END,
            submitted_at DESC,
            id DESC
        """
    ).fetchall()
    orders = []
    for row in rows:
        items = db.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        orders.append(serialize_order(row, items))
    return orders


def load_guest_names() -> list[dict]:
    rows = get_db().execute(
        """
        SELECT
            guest_names.id,
            guest_names.name,
            guest_names.created_at,
            guest_names.last_seen_at,
            COUNT(DISTINCT order_items.order_id) AS orders,
            COALESCE(SUM(order_items.quantity), 0) AS items,
            COALESCE(SUM(order_items.alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(order_items.alcohol_grams), 0) AS alcohol_grams
        FROM guest_names
        LEFT JOIN order_items
            ON order_items.recipient_name = guest_names.name COLLATE NOCASE
        WHERE guest_names.name != ? COLLATE NOCASE
        GROUP BY guest_names.id
        ORDER BY guest_names.name COLLATE NOCASE
        """,
        (UNASSIGNED_RECIPIENT,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "orders": row["orders"],
            "items": row["items"],
            "alcohol_ml": rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
            "alcohol_grams": rounded_float(Decimal(str(row["alcohol_grams"] or 0))),
            "standard_drinks": standard_drinks(row["alcohol_grams"] or 0),
            "created_at": iso_timestamp(row["created_at"]),
            "last_seen_at": iso_timestamp(row["last_seen_at"]),
        }
        for row in rows
    ]


def same_guest_name(left: str | None, right: str | None) -> bool:
    return clean_guest_name(left).casefold() == clean_guest_name(right).casefold()


def load_guest_name_detail(name_id: int) -> dict | None:
    db = get_db()
    guest = db.execute(
        """
        SELECT id, name, created_at, last_seen_at
        FROM guest_names
        WHERE id = ? AND name != ? COLLATE NOCASE
        """,
        (name_id, UNASSIGNED_RECIPIENT),
    ).fetchone()
    if guest is None:
        return None

    guest_name = guest["name"]
    history_rows = db.execute(
        """
        SELECT
            order_items.id,
            order_items.order_id,
            order_items.menu_item_id,
            order_items.name,
            order_items.category,
            order_items.quantity,
            order_items.recipient_name,
            order_items.recipe,
            order_items.alcohol_ml,
            order_items.alcohol_grams,
            order_items.completed_at,
            orders.guest_name AS orderer_name,
            orders.note,
            orders.status,
            orders.submitted_at,
            CASE
                WHEN orders.submitted_at >= datetime('now', '-4 hours') THEN 1
                ELSE 0
            END AS is_recent
        FROM order_items
        JOIN orders ON orders.id = order_items.order_id
        WHERE order_items.recipient_name = ? COLLATE NOCASE
            OR orders.guest_name = ? COLLATE NOCASE
        ORDER BY orders.submitted_at DESC, orders.id DESC, order_items.id DESC
        """,
        (guest_name, guest_name),
    ).fetchall()

    stats = {
        "items_for_guest": 0,
        "orders_for_guest": set(),
        "self_items": 0,
        "by_others_items": 0,
        "ordered_for_others_items": 0,
        "recent_items_4h": 0,
        "alcohol_ml": Decimal("0"),
        "alcohol_grams": Decimal("0"),
    }
    history = []
    for row in history_rows:
        for_guest = same_guest_name(row["recipient_name"], guest_name)
        by_guest = same_guest_name(row["orderer_name"], guest_name)
        quantity = row["quantity"] or 0
        alcohol_ml = Decimal(str(row["alcohol_ml"] or 0))
        alcohol_grams = Decimal(str(row["alcohol_grams"] or 0))
        if for_guest:
            stats["items_for_guest"] += quantity
            stats["orders_for_guest"].add(row["order_id"])
            stats["alcohol_ml"] += alcohol_ml
            stats["alcohol_grams"] += alcohol_grams
            if row["is_recent"]:
                stats["recent_items_4h"] += quantity
            if by_guest:
                stats["self_items"] += quantity
            else:
                stats["by_others_items"] += quantity
        elif by_guest:
            stats["ordered_for_others_items"] += quantity

        if for_guest and by_guest:
            relationship = "For self"
        elif for_guest:
            relationship = f"Ordered by {guest_name_label(row['orderer_name'])}"
        else:
            relationship = f"For {guest_name_label(row['recipient_name'])}"

        history.append(
            {
                "id": row["id"],
                "order_id": row["order_id"],
                "menu_item_id": row["menu_item_id"],
                "name": row["name"],
                "category": row["category"],
                "quantity": row["quantity"],
                "recipient_name": guest_name_label(row["recipient_name"]),
                "orderer_name": row["orderer_name"],
                "relationship": relationship,
                "recipe": parse_recipe_json(row["recipe"]),
                "alcohol_ml": rounded_float(alcohol_ml),
                "alcohol_grams": rounded_float(alcohol_grams),
                "standard_drinks": standard_drinks(alcohol_grams),
                "completed": row["completed_at"] is not None,
                "note": row["note"],
                "status": row["status"],
                "submitted_at": iso_timestamp(row["submitted_at"]),
            }
        )

    menu_items = db.execute(
        f"""
        SELECT id, name, category
        FROM menu_items
        WHERE available = 1 AND category != ? COLLATE NOCASE
        ORDER BY {category_order_sql()}, sort_order, id
        """,
        (UNASSIGNED_CATEGORY,),
    ).fetchall()

    orders_for_guest = len(stats["orders_for_guest"])
    alcohol_grams = stats["alcohol_grams"]
    return {
        "guest": {
            "id": guest["id"],
            "name": guest_name,
            "created_at": iso_timestamp(guest["created_at"]),
            "last_seen_at": iso_timestamp(guest["last_seen_at"]),
        },
        "stats": {
            "orders_for_guest": orders_for_guest,
            "items_for_guest": stats["items_for_guest"],
            "self_items": stats["self_items"],
            "by_others_items": stats["by_others_items"],
            "ordered_for_others_items": stats["ordered_for_others_items"],
            "recent_items_4h": stats["recent_items_4h"],
            "pace_per_hour": rounded_float(
                Decimal(str(stats["recent_items_4h"])) / Decimal("4")
            ),
            "alcohol_ml": rounded_float(stats["alcohol_ml"]),
            "alcohol_grams": rounded_float(alcohol_grams),
            "standard_drinks": standard_drinks(alcohol_grams),
        },
        "history": history,
        "menu_items": [dict(row) for row in menu_items],
    }


def order_queue_summary() -> dict:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_orders,
            SUM(status = 'new') AS active_orders,
            SUM(status = 'completed') AS completed_orders,
            COALESCE(SUM(item_count), 0) AS total_items,
            COALESCE(SUM(total_alcohol_ml), 0) AS total_alcohol_ml,
            COALESCE(SUM(total_alcohol_grams), 0) AS total_alcohol_grams
        FROM orders
        """
    ).fetchone()
    return {
        "total_orders": row["total_orders"],
        "active_orders": row["active_orders"] or 0,
        "completed_orders": row["completed_orders"] or 0,
        "total_items": row["total_items"] or 0,
        "total_alcohol_ml": rounded_float(Decimal(str(row["total_alcohol_ml"] or 0))),
        "total_alcohol_grams": rounded_float(Decimal(str(row["total_alcohol_grams"] or 0))),
        "standard_drinks": standard_drinks(row["total_alcohol_grams"] or 0),
    }


def build_guest_alcohol_timeline(db: sqlite3.Connection) -> dict:
    rows = db.execute(
        """
        SELECT
            recipient_name AS guest_name,
            SUBSTR(submitted_at, 1, 13) || ':00' AS hour,
            COALESCE(SUM(alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(alcohol_grams), 0) AS alcohol_grams
        FROM (
            SELECT
                CASE
                    WHEN TRIM(order_items.recipient_name) = '' THEN ?
                    ELSE order_items.recipient_name
                END AS recipient_name,
                orders.submitted_at,
                order_items.alcohol_ml,
                order_items.alcohol_grams
            FROM order_items
            JOIN orders ON orders.id = order_items.order_id
            WHERE order_items.alcohol_ml > 0
        )
        GROUP BY recipient_name COLLATE NOCASE, hour
        ORDER BY hour, guest_name COLLATE NOCASE
        """,
        (UNASSIGNED_RECIPIENT,),
    ).fetchall()
    if not rows:
        return {"labels": [], "series": []}

    hours = sorted({row["hour"] for row in rows})
    labels = [iso_timestamp(hour) for hour in hours]
    totals_ml: dict[str, Decimal] = {}
    totals_grams: dict[str, Decimal] = {}
    by_guest_hour: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
    for row in rows:
        guest_name = row["guest_name"]
        alcohol_ml = Decimal(str(row["alcohol_ml"] or 0))
        grams = Decimal(str(row["alcohol_grams"] or 0))
        totals_ml[guest_name] = totals_ml.get(guest_name, Decimal("0")) + alcohol_ml
        totals_grams[guest_name] = totals_grams.get(guest_name, Decimal("0")) + grams
        by_guest_hour.setdefault(guest_name, {})[row["hour"]] = (alcohol_ml, grams)

    top_guest_names = sorted(
        totals_ml,
        key=lambda guest_name: (-totals_ml[guest_name], guest_name.casefold()),
    )[:6]
    series = []
    for guest_name in top_guest_names:
        cumulative_ml = Decimal("0")
        cumulative_grams = Decimal("0")
        points = []
        for hour in hours:
            hour_ml, hour_grams = by_guest_hour.get(guest_name, {}).get(
                hour, (Decimal("0"), Decimal("0"))
            )
            cumulative_ml += hour_ml
            cumulative_grams += hour_grams
            points.append(
                {
                    "hour": iso_timestamp(hour),
                    "alcohol_ml": rounded_float(cumulative_ml),
                    "alcohol_grams": rounded_float(cumulative_grams),
                    "standard_drinks": standard_drinks(cumulative_grams),
                }
            )
        series.append(
            {
                "guest_name": guest_name,
                "alcohol_ml": rounded_float(totals_ml[guest_name]),
                "alcohol_grams": rounded_float(totals_grams[guest_name]),
                "standard_drinks": standard_drinks(totals_grams[guest_name]),
                "points": points,
            }
        )
    return {"labels": labels, "series": series}


def build_order_stats() -> dict:
    db = get_db()
    summary = order_queue_summary()
    guest_rows = db.execute(
        """
        SELECT
            recipient_name AS guest_name,
            COUNT(DISTINCT order_id) AS orders,
            COALESCE(SUM(quantity), 0) AS items,
            COALESCE(SUM(alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(alcohol_grams), 0) AS alcohol_grams,
            COALESCE(SUM(
                CASE
                    WHEN submitted_at >= datetime('now', '-4 hours') THEN quantity
                    ELSE 0
                END
            ), 0) AS recent_items_4h,
            COUNT(DISTINCT
                CASE
                    WHEN submitted_at >= datetime('now', '-4 hours') THEN order_id
                END
            ) AS recent_orders_4h,
            COALESCE(SUM(
                CASE
                    WHEN orderer_name COLLATE NOCASE = recipient_name THEN quantity
                    ELSE 0
                END
            ), 0) AS self_items,
            COUNT(DISTINCT
                CASE
                    WHEN orderer_name COLLATE NOCASE = recipient_name THEN order_id
                END
            ) AS self_orders,
            MIN(submitted_at) AS first_order_at,
            MAX(submitted_at) AS last_order_at
        FROM (
            SELECT
                CASE
                    WHEN TRIM(order_items.recipient_name) = '' THEN ?
                    ELSE order_items.recipient_name
                END AS recipient_name,
                orders.guest_name AS orderer_name,
                order_items.order_id,
                order_items.quantity,
                order_items.alcohol_ml,
                order_items.alcohol_grams,
                orders.submitted_at
            FROM order_items
            JOIN orders ON orders.id = order_items.order_id
        )
        GROUP BY recipient_name COLLATE NOCASE
        ORDER BY items DESC, orders DESC, guest_name COLLATE NOCASE
        """,
        (UNASSIGNED_RECIPIENT,),
    ).fetchall()
    item_rows = db.execute(
        """
        SELECT
            name,
            category,
            COALESCE(SUM(quantity), 0) AS quantity,
            COALESCE(SUM(alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(alcohol_grams), 0) AS alcohol_grams
        FROM order_items
        GROUP BY name, category
        ORDER BY quantity DESC, name COLLATE NOCASE
        LIMIT 12
        """
    ).fetchall()
    hour_rows = db.execute(
        """
        SELECT
            SUBSTR(submitted_at, 1, 13) || ':00' AS hour,
            COUNT(*) AS orders,
            COALESCE(SUM(item_count), 0) AS items,
            COALESCE(SUM(total_alcohol_ml), 0) AS alcohol_ml
        FROM orders
        GROUP BY hour
        ORDER BY hour
        """
    ).fetchall()
    category_rows = db.execute(
        """
        SELECT
            category,
            COALESCE(SUM(quantity), 0) AS quantity,
            COALESCE(SUM(alcohol_ml), 0) AS alcohol_ml,
            COALESCE(SUM(alcohol_grams), 0) AS alcohol_grams
        FROM order_items
        GROUP BY category
        ORDER BY quantity DESC, category COLLATE NOCASE
        """
    ).fetchall()
    biggest_order_row = db.execute(
        """
        SELECT
            guest_name,
            item_count,
            total_alcohol_grams,
            submitted_at
        FROM orders
        ORDER BY item_count DESC, submitted_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    guests = [
        {
            "guest_name": row["guest_name"],
            "orders": row["orders"],
            "items": row["items"],
            "alcohol_ml": rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
            "alcohol_grams": rounded_float(Decimal(str(row["alcohol_grams"] or 0))),
            "standard_drinks": standard_drinks(row["alcohol_grams"] or 0),
            "recent_items_4h": row["recent_items_4h"] or 0,
            "recent_orders_4h": row["recent_orders_4h"] or 0,
            "self_items": row["self_items"] or 0,
            "self_orders": row["self_orders"] or 0,
            "by_others_items": (row["items"] or 0) - (row["self_items"] or 0),
            "first_order_at": iso_timestamp(row["first_order_at"]),
            "last_order_at": iso_timestamp(row["last_order_at"]),
        }
        for row in guest_rows
    ]
    items = [
        {
            "name": row["name"],
            "category": row["category"],
            "quantity": row["quantity"],
            "alcohol_ml": rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
            "alcohol_grams": rounded_float(Decimal(str(row["alcohol_grams"] or 0))),
            "standard_drinks": standard_drinks(row["alcohol_grams"] or 0),
        }
        for row in item_rows
    ]
    timeline = [
        {
            "hour": iso_timestamp(row["hour"]),
            "orders": row["orders"],
            "items": row["items"],
            "alcohol_ml": rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
        }
        for row in hour_rows
    ]
    categories = [
        {
            "category": row["category"],
            "quantity": row["quantity"],
            "alcohol_ml": rounded_float(Decimal(str(row["alcohol_ml"] or 0))),
            "alcohol_grams": rounded_float(Decimal(str(row["alcohol_grams"] or 0))),
            "standard_drinks": standard_drinks(row["alcohol_grams"] or 0),
        }
        for row in category_rows
    ]
    total_orders = summary["total_orders"] or 0
    avg_items_per_order = (
        rounded_float(Decimal(str(summary["total_items"])) / Decimal(str(total_orders)))
        if total_orders
        else 0
    )
    completion_rate = (
        rounded_float(
            Decimal(str(summary["completed_orders"])) / Decimal(str(total_orders)) * 100
        )
        if total_orders
        else 0
    )
    peak_hour = max(timeline, key=lambda row: (row["items"], row["orders"]), default=None)
    biggest_order = (
        {
            "guest_name": biggest_order_row["guest_name"],
            "item_count": biggest_order_row["item_count"],
            "standard_drinks": standard_drinks(biggest_order_row["total_alcohol_grams"] or 0),
            "submitted_at": iso_timestamp(biggest_order_row["submitted_at"]),
        }
        if biggest_order_row
        else None
    )
    return {
        "summary": summary,
        "highlights": {
            "unique_guests": len(
                [
                    guest
                    for guest in guests
                    if not is_reserved_guest_name(guest["guest_name"])
                ]
            ),
            "top_guest": guests[0] if guests else None,
            "top_item": items[0] if items else None,
            "top_category": categories[0] if categories else None,
            "peak_hour": peak_hour,
            "biggest_order": biggest_order,
            "avg_items_per_order": avg_items_per_order,
            "completion_rate": completion_rate,
        },
        "guests": guests,
        "items": items,
        "categories": categories,
        "timeline": timeline,
        "guest_alcohol_timeline": build_guest_alcohol_timeline(db),
    }


def parse_basket_items(value: str | None) -> list[dict]:
    try:
        payload = json.loads(value or "")
    except json.JSONDecodeError as error:
        raise ValueError(
            "Your basket could not be read. Return to the menu and try again."
        ) from error

    if not isinstance(payload, list) or not payload:
        raise ValueError("Your basket is empty.")
    if len(payload) > MAX_BASKET_DISTINCT_ITEMS:
        raise ValueError(
            f"A basket may contain at most {MAX_BASKET_DISTINCT_ITEMS} different items."
        )

    parsed = []
    seen_ids = set()
    total_quantity = 0
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("Your basket contains an invalid item.")
        item_id = entry.get("id")
        quantity = entry.get("quantity")
        if (
            isinstance(item_id, bool)
            or not isinstance(item_id, int)
            or item_id < 1
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or not 1 <= quantity <= MAX_BASKET_QUANTITY
        ):
            raise ValueError("Your basket contains an invalid quantity.")
        if item_id in seen_ids:
            raise ValueError("Your basket contains a duplicate item.")
        raw_recipients = entry.get("recipients")
        if raw_recipients is None:
            raise ValueError("Each ordered drink needs one name.")
        if not isinstance(raw_recipients, list):
            raise ValueError("Your basket contains invalid drink names.")
        if len(raw_recipients) != quantity:
            raise ValueError("Each ordered drink needs one name.")
        recipients = []
        for raw_recipient in raw_recipients:
            recipient_name = normalize_recipient_name(raw_recipient)
            if not recipient_name:
                raise ValueError("Each ordered drink needs one name.")
            recipients.append(recipient_name)
        seen_ids.add(item_id)
        total_quantity += quantity
        parsed.append({"id": item_id, "quantity": quantity, "recipients": recipients})

    if total_quantity > MAX_BASKET_TOTAL_ITEMS:
        raise ValueError(
            f"A basket may contain at most {MAX_BASKET_TOTAL_ITEMS} items."
        )
    return parsed


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

    @app.route("/order/basket", methods=("GET", "POST"))
    def order_basket():
        catalog_rows = get_db().execute(
            f"""
            SELECT id, name, category, recipe
            FROM menu_items
            WHERE available = 1 AND category != ? COLLATE NOCASE
            ORDER BY {category_order_sql()}, sort_order, id
            """,
            (UNASSIGNED_CATEGORY,),
        ).fetchall()
        catalog = []
        for row in catalog_rows:
            item = dict(row)
            item["recipe"] = parse_recipe_json(item["recipe"])
            catalog.append(item)
        catalog_by_id = {item["id"]: item for item in catalog}
        public_catalog = [
            {"id": item["id"], "name": item["name"], "category": item["category"]}
            for item in catalog
        ]
        guest_name = normalize_stored_guest_name(
            request.cookies.get(GUEST_NAME_COOKIE), allow_empty=True
        )
        note = ""

        def render_basket(status: int = 200):
            rendered = render_template(
                "basket.html",
                catalog=public_catalog,
                guest_name=guest_name,
                guest_names=load_guest_name_options(),
                note=note,
            )
            return (rendered, status) if status != 200 else rendered

        if request.method == "GET":
            return render_basket()

        submitted_guest_name = request.form.get("guest_name", "")
        guest_name = clean_guest_name(submitted_guest_name)
        note = request.form.get("note", "").strip()

        try:
            guest_name = canonical_guest_name(normalize_orderer_name(submitted_guest_name))
            submitted_items = parse_basket_items(request.form.get("basket_items"))
        except ValueError as error:
            flash(str(error), "error")
            return render_basket(400)

        if len(note) > 300:
            flash("The note may not exceed 300 characters.", "error")
            return render_basket(400)

        items = []
        for submitted_item in submitted_items:
            item_id = submitted_item["id"]
            quantity = submitted_item["quantity"]
            item = catalog_by_id.get(item_id)
            if item is None:
                flash(
                    "One or more basket items are no longer available. Review your basket.",
                    "error",
                )
                return render_basket(400)
            recipients = [
                canonical_guest_name(recipient)
                for recipient in submitted_item["recipients"]
            ]
            items.append({**item, "quantity": quantity, "recipients": recipients})

        message = format_basket_message(items, guest_name, note)
        if len(message.encode("utf-8")) > MAX_PUSHOVER_MESSAGE_LENGTH:
            flash(
                "This basket is too long to send. Remove a few items or shorten the note.",
                "error",
            )
            return render_basket(400)

        now = time.time()
        last_order_at = session.get("last_order_at", 0)
        if now - last_order_at < current_app.config["ORDER_COOLDOWN_SECONDS"]:
            flash("Please wait a few seconds before ordering again.", "error")
            return render_basket(429)

        create_order(guest_name, note, items, "basket")
        notification_failed = False
        try:
            send_pushover_basket_order(items, guest_name, note)
        except PushoverError as error:
            notification_failed = True
            current_app.logger.warning("Could not send basket order: %s", error)
        session["last_order_at"] = now
        item_count = sum(item["quantity"] for item in items)
        recipient_summary = format_guest_name_list(
            basket_recipient_names(items, guest_name)
        )
        if notification_failed:
            flash(
                f"Basket order received for {recipient_summary}: {item_count} "
                f"item{'s' if item_count != 1 else ''}. The host notification "
                "failed, so ask the host to check the queue.",
                "success",
            )
        else:
            flash(
                f"Basket order sent for {recipient_summary}: {item_count} "
                f"item{'s' if item_count != 1 else ''}.",
                "success",
            )
        response = redirect(url_for("menu", basket_sent=1))
        response.set_cookie(
            GUEST_NAME_COOKIE,
            guest_name,
            max_age=GUEST_NAME_COOKIE_MAX_AGE,
            httponly=True,
            secure=current_app.config["SESSION_COOKIE_SECURE"] or request.is_secure,
            samesite="Lax",
        )
        return response

    @app.route("/order/item/<int:item_id>", methods=("GET", "POST"))
    def order_item(item_id: int):
        item = get_db().execute(
            """
            SELECT name, description, category, available, recipe
            FROM menu_items WHERE id = ?
            """,
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
            guest_name = normalize_stored_guest_name(
                request.cookies.get(GUEST_NAME_COOKIE), allow_empty=True
            )
            return render_template(
                "order.html",
                item=item,
                guest_name=guest_name,
                guest_names=load_guest_name_options(),
                note="",
            )

        note = request.form.get("note", "").strip()
        try:
            guest_name = canonical_guest_name(
                normalize_orderer_name(request.form.get("guest_name", ""))
            )
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "order.html",
                item=item,
                guest_name=clean_guest_name(request.form.get("guest_name", "")),
                guest_names=load_guest_name_options(),
                note=note,
            ), 400
        if len(note) > 300:
            flash("The note may not exceed 300 characters.", "error")
            return render_template(
                "order.html",
                item=item,
                guest_name=guest_name,
                guest_names=load_guest_name_options(),
                note=note,
            ), 400

        now = time.time()
        last_order_at = session.get("last_order_at", 0)
        if now - last_order_at < current_app.config["ORDER_COOLDOWN_SECONDS"]:
            flash("Please wait a few seconds before ordering again.", "error")
            return render_template(
                "order.html",
                item=item,
                guest_name=guest_name,
                guest_names=load_guest_name_options(),
                note=note,
            ), 429

        recipe = parse_recipe_json(item["recipe"])
        message = format_single_order_message(
            item["name"], item["category"], note, recipe
        )
        if len(message.encode("utf-8")) > MAX_PUSHOVER_MESSAGE_LENGTH:
            flash(
                "This order is too long to send. Shorten the note or ask the host "
                "to shorten the recipe.",
                "error",
            )
            return render_template(
                "order.html",
                item=item,
                guest_name=guest_name,
                guest_names=load_guest_name_options(),
                note=note,
            ), 400

        create_order(
            guest_name,
            note,
            [
                {
                    "id": item_id,
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": 1,
                    "recipe": recipe,
                }
            ],
            "single",
        )
        notification_failed = False
        try:
            send_pushover_order(
                item["name"], item["category"], guest_name, note, recipe
            )
        except PushoverError as error:
            notification_failed = True
            current_app.logger.warning("Could not send order: %s", error)
        session["last_order_at"] = now
        if notification_failed:
            flash(
                f"Order received for {guest_name}: {item['name']}. The host "
                "notification failed, so ask the host to check the queue.",
                "success",
            )
        else:
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

    @app.get("/host/orders")
    @host_required
    def host_orders():
        return render_template(
            "host_orders.html",
            orders_json=load_orders("active"),
            summary=order_queue_summary(),
        )

    @app.get("/host/orders.json")
    @host_required
    def host_orders_json():
        status = request.args.get("status", "active")
        if status not in {"active", "completed", "all"}:
            status = "active"
        return {
            "orders": load_orders(status),
            "summary": order_queue_summary(),
            "status": status,
            "generated_at": time.time(),
        }

    @app.post("/host/orders/<int:order_id>/complete")
    @host_required
    def complete_order(order_id: int):
        db = get_db()
        existing = db.execute(
            "SELECT id, status FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if existing is None:
            abort(404)
        db.execute(
            """
            UPDATE order_items
            SET completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
            WHERE order_id = ?
            """,
            (order_id,),
        )
        if existing["status"] != "completed":
            db.execute(
                """
                UPDATE orders
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (order_id,),
            )
        db.commit()
        return {"ok": True, "order_id": order_id}

    @app.post("/host/orders/<int:order_id>/items/<int:item_id>/complete")
    @host_required
    def complete_order_item(order_id: int, item_id: int):
        completed = request.form.get("completed", "1").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
        db = get_db()
        existing = db.execute(
            "SELECT id FROM order_items WHERE id = ? AND order_id = ?",
            (item_id, order_id),
        ).fetchone()
        if existing is None:
            abort(404)
        if completed:
            db.execute(
                """
                UPDATE order_items
                SET completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (item_id,),
            )
        else:
            db.execute(
                "UPDATE order_items SET completed_at = NULL WHERE id = ?",
                (item_id,),
            )
        order_status = sync_order_status_from_items(order_id)
        db.commit()
        return {
            "ok": True,
            "order_id": order_id,
            "item_id": item_id,
            "completed": completed,
            "order_status": order_status,
        }

    @app.post("/host/orders/<int:order_id>/delete")
    @host_required
    def delete_order(order_id: int):
        db = get_db()
        existing = db.execute(
            "SELECT id FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if existing is None:
            abort(404)
        db.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        db.commit()
        return {"ok": True, "order_id": order_id}

    @app.post("/host/orders/clear")
    @host_required
    def clear_orders():
        action = request.form.get("action", "completed")
        db = get_db()
        if action == "all":
            cleared = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            db.execute("DELETE FROM order_items")
            db.execute("DELETE FROM orders")
        else:
            cleared = db.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'completed'"
            ).fetchone()[0]
            db.execute(
                """
                DELETE FROM order_items
                WHERE order_id IN (
                    SELECT id FROM orders WHERE status = 'completed'
                )
                """
            )
            db.execute("DELETE FROM orders WHERE status = 'completed'")
        db.commit()
        return {"ok": True, "cleared": cleared, "action": action}

    @app.get("/host/names")
    @host_required
    def host_names():
        return render_template("host_names.html", guest_names=load_guest_names())

    @app.get("/host/names/<int:name_id>")
    @host_required
    def host_name_detail(name_id: int):
        detail = load_guest_name_detail(name_id)
        if detail is None:
            abort(404)
        return render_template("host_name_detail.html", **detail)

    @app.post("/host/names/<int:name_id>/add-drink")
    @host_required
    def add_guest_drink(name_id: int):
        detail = load_guest_name_detail(name_id)
        if detail is None:
            abort(404)

        menu_item_id = request.form.get("menu_item_id", type=int)
        quantity = request.form.get("quantity", type=int) or 1
        if quantity < 1 or quantity > MAX_BASKET_QUANTITY:
            flash(f"Choose between 1 and {MAX_BASKET_QUANTITY} drinks.", "error")
            return redirect(url_for("host_name_detail", name_id=name_id))

        item = get_db().execute(
            """
            SELECT id, name, category, recipe
            FROM menu_items
            WHERE id = ?
                AND available = 1
                AND category != ? COLLATE NOCASE
            """,
            (menu_item_id, UNASSIGNED_CATEGORY),
        ).fetchone()
        if item is None:
            flash("Choose an available menu item.", "error")
            return redirect(url_for("host_name_detail", name_id=name_id))

        guest_name = detail["guest"]["name"]
        create_order(
            guest_name,
            "Added by host from the names page.",
            [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "quantity": quantity,
                    "recipients": [guest_name] * quantity,
                    "recipe": parse_recipe_json(item["recipe"]),
                }
            ],
            "single",
        )
        flash(f"Added {quantity}x {item['name']} for {guest_name}.", "success")
        return redirect(url_for("host_name_detail", name_id=name_id))

    @app.post("/host/names/<int:name_id>/items/<int:item_id>/delete")
    @host_required
    def remove_guest_drink(name_id: int, item_id: int):
        detail = load_guest_name_detail(name_id)
        if detail is None:
            abort(404)
        guest_name = detail["guest"]["name"]
        item = get_db().execute(
            """
            SELECT order_items.id, order_items.name
            FROM order_items
            JOIN orders ON orders.id = order_items.order_id
            WHERE order_items.id = ?
                AND (
                    order_items.recipient_name = ? COLLATE NOCASE
                    OR orders.guest_name = ? COLLATE NOCASE
                )
            """,
            (item_id, guest_name, guest_name),
        ).fetchone()
        if item is None:
            abort(404)
        remove_one_order_item(item_id)
        get_db().commit()
        flash(f"Removed one {item['name']}.", "success")
        return redirect(url_for("host_name_detail", name_id=name_id))

    @app.post("/host/names/<int:name_id>/delete")
    @host_required
    def delete_guest_name(name_id: int):
        db = get_db()
        existing = db.execute(
            "SELECT id, name FROM guest_names WHERE id = ?", (name_id,)
        ).fetchone()
        if existing is None:
            abort(404)
        db.execute(
            """
            UPDATE order_items
            SET recipient_name = ''
            WHERE recipient_name = ? COLLATE NOCASE
            """,
            (existing["name"],),
        )
        db.execute("DELETE FROM guest_names WHERE id = ?", (name_id,))
        db.commit()
        flash(
            f"{existing['name']} was removed. Assigned drinks now show as unassigned.",
            "success",
        )
        return redirect(url_for("host_names"))

    @app.get("/host/stats")
    @host_required
    def host_stats():
        return render_template("host_stats.html", stats_json=build_order_stats())

    @app.get("/host/stats.json")
    @host_required
    def host_stats_json():
        return {"stats": build_order_stats(), "generated_at": time.time()}

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
            item["recipe"] = parse_recipe_json(item["recipe"])
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
        image_focus_x = parse_focus(request.form.get("image_focus_x"))
        image_focus_y = parse_focus(request.form.get("image_focus_y"))

        if not name or not category:
            flash("Name and category are required.", "error")
            return redirect(url_for("host_editor"))

        try:
            recipe = parse_recipe_form()
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("host_editor"))
        stored_recipe = recipe_json(recipe)

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
                SET name = ?, description = ?, category = ?, image = ?, available = ?,
                    sort_order = ?, recipe = ?, image_focus_x = ?, image_focus_y = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    description,
                    category,
                    image,
                    available,
                    sort_order,
                    stored_recipe,
                    image_focus_x,
                    image_focus_y,
                    item_id,
                ),
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
                    (name, description, category, image, available, sort_order, recipe,
                     image_focus_x, image_focus_y)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    description,
                    category,
                    image,
                    available,
                    next_order,
                    stored_recipe,
                    image_focus_x,
                    image_focus_y,
                ),
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
        writer.writerow(
            (
                "Espresso Martini",
                "Vodka, espresso, coffee liqueur.",
                "Cocktails",
                "yes",
                "",
                "images/espresso-martini.jpg",
                "50",
                "40",
                "1",
                "1",
                recipe_json(
                    [
                        {"name": "Vodka", "ml": "40"},
                        {"name": "Espresso", "ml": "30"},
                        {"name": "Coffee liqueur", "ml": "20", "abv": "20"},
                        {"name": "Ice", "ml": ""},
                    ]
                ),
            )
        )
        writer.writerow(
            (
                "Sparkling Water",
                "Cold and fizzy.",
                "Booze, Beer & Wine",
                "yes",
                "https://example.com/water.jpg",
                "",
                "50",
                "50",
                "2",
                "1",
                "[]",
            )
        )
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
                "image_focus_x": item["image_focus_x"],
                "image_focus_y": item["image_focus_y"],
                "category_order": category_orders.get(item["category"].casefold(), ""),
                "sort_order": item["sort_order"],
                "recipe": recipe_json(parse_recipe_json(item["recipe"])),
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
    prepared_items = []
    saved_images = []
    skipped = 0

    try:
        for row_number, row in enumerate(rows, start=1):
            name = " ".join(row.get("name", "").split())
            raw_category = clean_category_name(row.get("category", ""))
            if not name or not raw_category:
                skipped += 1
                continue

            if raw_category.casefold() == UNASSIGNED_CATEGORY.casefold():
                category = UNASSIGNED_CATEGORY
            else:
                category = canonical_category(raw_category)
                if category is None:
                    if category_name_error(raw_category):
                        skipped += 1
                        continue
                    category = raw_category

            try:
                recipe = recipe_json(parse_recipe_json(row.get("recipe")))
            except ValueError:
                skipped += 1
                continue

            image = clean_image_reference(row.get("image_url"))
            image_filename = row.get("image_filename", "").lstrip("./")
            if image_filename:
                match = image_files.get(image_filename.casefold()) or image_files.get(
                    PurePosixPath(image_filename).name.casefold()
                )
                if match is None:
                    skipped += 1
                    continue
                try:
                    image = save_image_bytes(*match)
                except ValueError:
                    skipped += 1
                    continue
                saved_images.append(image)

            try:
                category_order = int(row.get("category_order") or row_number)
            except ValueError:
                category_order = row_number
            try:
                sort_order = int(row.get("sort_order") or row_number)
            except ValueError:
                sort_order = row_number

            prepared_items.append(
                {
                    "name": name,
                    "description": row.get("description", ""),
                    "category": category,
                    "available": parse_available(row.get("available")),
                    "recipe": recipe,
                    "image_focus_x": parse_focus(row.get("image_focus_x")),
                    "image_focus_y": parse_focus(row.get("image_focus_y")),
                    "image": image,
                    "category_order": category_order,
                    "sort_order": sort_order,
                    "row_number": row_number,
                }
            )

        db.execute("BEGIN IMMEDIATE")
        existing_categories = {
            row["name"].casefold(): row["name"]
            for row in db.execute("SELECT name FROM menu_categories").fetchall()
        }
        new_categories = {}
        for item in prepared_items:
            category = item["category"]
            key = category.casefold()
            if key == UNASSIGNED_CATEGORY.casefold() or key in existing_categories:
                continue
            current = new_categories.get(key)
            if current is None or item["category_order"] < current[1]:
                new_categories[key] = (category, item["category_order"])

        next_category_order = db.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM menu_categories"
        ).fetchone()[0]
        for key, (category, _requested_order) in sorted(
            new_categories.items(), key=lambda entry: (entry[1][1], entry[1][0].casefold())
        ):
            next_category_order += 1
            db.execute(
                "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
                (category, next_category_order),
            )
            existing_categories[key] = category

        items_by_category: dict[str, list[dict[str, object]]] = {}
        for item in prepared_items:
            key = item["category"].casefold()
            if key != UNASSIGNED_CATEGORY.casefold():
                item["category"] = existing_categories[key]
            items_by_category.setdefault(key, []).append(item)

        for category_items in items_by_category.values():
            category_items.sort(
                key=lambda item: (item["sort_order"], item["row_number"])
            )
            category = category_items[0]["category"]
            next_item_order = db.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM menu_items WHERE category = ?",
                (category,),
            ).fetchone()[0]
            for item in category_items:
                next_item_order += 1
                db.execute(
                    """
                    INSERT INTO menu_items
                        (name, description, category, image, available, sort_order, recipe,
                         image_focus_x, image_focus_y)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["name"],
                        item["description"],
                        item["category"],
                        item["image"],
                        item["available"],
                        next_item_order,
                        item["recipe"],
                        item["image_focus_x"],
                        item["image_focus_y"],
                    ),
                )
        db.commit()
    except Exception:
        db.rollback()
        for image in saved_images:
            delete_uploaded_image(image)
        raise

    return len(prepared_items), skipped


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
        try:
            recipe = recipe_json(parse_recipe_json(row.get("recipe")))
        except ValueError as error:
            raise ValueError(
                f"Invalid recipe on menu.csv row {row_number}: {error}"
            ) from error
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
                "recipe": recipe,
                "image_focus_x": parse_focus(row.get("image_focus_x")),
                "image_focus_y": parse_focus(row.get("image_focus_y")),
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
                (name, description, category, image, available, sort_order, recipe,
                 image_focus_x, image_focus_y)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["name"],
                    item["description"],
                    item["category"],
                    item["image"],
                    item["available"],
                    item["sort_order"],
                    item["recipe"],
                    item["image_focus_x"],
                    item["image_focus_y"],
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
