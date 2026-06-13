from __future__ import annotations

import csv
import functools
import hmac
import io
import os
import secrets
import sqlite3
import uuid
import zipfile
from pathlib import Path, PurePosixPath

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

CATEGORIES = ("Cocktails", "Booze, Beer & Wine", "Snacks")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

SEED_ITEMS = (
    (
        "Negroni",
        "Gin, Campari, sweet vermouth, and an orange twist.",
        "Cocktails",
        "/static/seed/negroni.jpg",
        1,
    ),
    (
        "Paloma",
        "Tequila, grapefruit, lime, soda, and a pinch of salt.",
        "Cocktails",
        "/static/seed/paloma.jpg",
        1,
    ),
    (
        "Cold Beer",
        "A cold, crisp selection of lager and pale ale.",
        "Booze, Beer & Wine",
        "/static/seed/cold-beer.jpg",
        1,
    ),
    (
        "Red Wine",
        "The host's smooth and balanced house red.",
        "Booze, Beer & Wine",
        "/static/seed/red-wine.jpg",
        1,
    ),
    (
        "Olives",
        "Marinated mixed olives with herbs and citrus.",
        "Snacks",
        "/static/seed/olives.jpg",
        1,
    ),
    (
        "Crisps",
        "Sea salt potato crisps. Simple and crunchy.",
        "Snacks",
        "/static/seed/crisps.jpg",
        1,
    ),
    (
        "Cheese Board",
        "A selection of cheeses, crackers, nuts, and chutney.",
        "Snacks",
        "/static/seed/cheese-board.jpg",
        1,
    ),
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
    app.jinja_env.globals.update(csrf_token=csrf_token, categories=CATEGORIES)

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
        """
    )
    db.execute("BEGIN IMMEDIATE")
    count = db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
    if count == 0:
        db.executemany(
            """
            INSERT INTO menu_items
                (name, description, category, image, available, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(*item, index) for index, item in enumerate(SEED_ITEMS, start=1)],
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


def canonical_category(value: str) -> str | None:
    cleaned = " ".join((value or "").strip().split()).casefold()
    for category in CATEGORIES:
        if cleaned == category.casefold():
            return category
    aliases = {
        "booze": "Booze, Beer & Wine",
        "beer": "Booze, Beer & Wine",
        "wine": "Booze, Beer & Wine",
        "drinks": "Booze, Beer & Wine",
        "snack": "Snacks",
        "cocktail": "Cocktails",
    }
    return aliases.get(cleaned)


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
    return "CASE category WHEN 'Cocktails' THEN 1 WHEN 'Booze, Beer & Wine' THEN 2 WHEN 'Snacks' THEN 3 ELSE 4 END"


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
        rows = get_db().execute(
            f"SELECT * FROM menu_items ORDER BY {category_order_sql()}, sort_order, id"
        ).fetchall()
        grouped = {category: [] for category in CATEGORIES}
        for row in rows:
            grouped.setdefault(row["category"], []).append(row)
        available_count = sum(row["available"] for row in rows)
        return render_template(
            "menu.html",
            grouped=grouped,
            available_count=available_count,
            total_count=len(rows),
        )

    @app.get("/health")
    def health():
        get_db().execute("SELECT 1").fetchone()
        return {"status": "ok"}

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
        selected_category = request.args.get("category", "All items")
        selected_status = request.args.get("status", "all")
        conditions = []
        values = []
        if selected_category in CATEGORIES:
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
        all_rows = get_db().execute("SELECT category, available FROM menu_items").fetchall()
        counts = {
            "all": len(all_rows),
            "available": sum(row["available"] for row in all_rows),
            "out": sum(not row["available"] for row in all_rows),
            **{category: sum(row["category"] == category for row in all_rows) for category in CATEGORIES},
        }
        items_json = [dict(row) for row in rows]
        return render_template(
            "host.html",
            items=rows,
            items_json=items_json,
            counts=counts,
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
            old = db.execute("SELECT image FROM menu_items WHERE id = ?", (item_id,)).fetchone()
            if old is None:
                abort(404)
            db.execute(
                """
                UPDATE menu_items
                SET name = ?, description = ?, category = ?, image = ?, available = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, description, category, image, available, item_id),
            )
            db.commit()
            if old["image"] != image:
                delete_uploaded_image(old["image"])
            flash(f"Updated {name}.", "success")
        else:
            next_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM menu_items").fetchone()[0]
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

    @app.post("/host/item/<int:item_id>/delete")
    @host_required
    def delete_item(item_id: int):
        db = get_db()
        item = db.execute("SELECT name, image FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        db.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
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
