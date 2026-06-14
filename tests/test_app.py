import csv
import io
import re
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from app import create_app, send_pushover_order


TOKEN_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


class MenuAppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "ADMIN_PASSWORD": "party-password",
                "DATA_DIR": self.temp_dir.name,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def token_from(self, path):
        response = self.client.get(path)
        match = TOKEN_PATTERN.search(response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def login(self):
        token = self.token_from("/host/login")
        response = self.client.post(
            "/host/login",
            data={"password": "party-password", "csrf_token": token},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Menu editor", response.data)

    def test_public_menu_and_health(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tonight's Menu", response.data)
        self.assertIn(b"Espresso Martini", response.data)
        self.assertIn(b"Hard Drinks", response.data)
        self.assertIn(b"Soft Drinks", response.data)
        self.assertIn(b"25 items available", response.data)
        self.assertEqual(response.data.count(b'class="menu-order-button"'), 25)
        self.assertIn(b'aria-label="Order Espresso Martini"', response.data)
        self.assertIn(b'id="menu-search-input"', response.data)
        self.assertIn(b"Search names and descriptions", response.data)
        self.assertRegex(response.data, rb'/static/js/menu\.js\?v=\d+')
        image_paths = re.findall(rb'<img src="([^"]+)"', response.data)
        self.assertEqual(len(image_paths), 25)
        for image_path in image_paths:
            image_response = self.client.get(image_path.decode())
            self.assertEqual(image_response.status_code, 200)
            image_response.close()
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})

    def test_pushover_order_payload(self):
        self.app.config.update(
            PUSHOVER_API_TOKEN="application-token",
            PUSHOVER_USER_KEY="user-key",
        )
        response = io.BytesIO(b'{"status": 1}')

        with self.app.app_context(), patch("app.urlopen", return_value=response) as mocked:
            send_pushover_order(
                "Espresso Martini", "Cocktails", "Noah", "Less ice, please"
            )

        pushover_request = mocked.call_args.args[0]
        payload = parse_qs(pushover_request.data.decode())
        self.assertEqual(payload["token"], ["application-token"])
        self.assertEqual(payload["user"], ["user-key"])
        self.assertEqual(payload["title"], ["Order from Noah"])
        self.assertEqual(
            payload["message"],
            ["Item: Espresso Martini\nCategory: Cocktails\nNote: Less ice, please"],
        )
        self.assertEqual(mocked.call_args.kwargs["timeout"], 5)

    def test_guest_can_order_available_item(self):
        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]

        order_page = self.client.get(f"/order/item/{item_id}")
        self.assertIn(b"Your name", order_page.data)
        self.assertIn(b"Note", order_page.data)
        token = self.token_from(f"/order/item/{item_id}")
        with patch("app.send_pushover_order") as send_order:
            response = self.client.post(
                f"/order/item/{item_id}",
                data={
                    "csrf_token": token,
                    "guest_name": "Noah",
                    "note": "Less ice, please",
                },
                follow_redirects=True,
            )

        self.assertIn(b"Order sent for Noah: Espresso Martini.", response.data)
        send_order.assert_called_once_with(
            "Espresso Martini", "Cocktails", "Noah", "Less ice, please"
        )

    def test_successful_order_remembers_only_the_latest_guest_name(self):
        self.app.config["ORDER_COOLDOWN_SECONDS"] = 0
        with self.app.app_context():
            from app import get_db

            item_ids = {
                row["name"]: row["id"]
                for row in get_db()
                .execute(
                    "SELECT id, name FROM menu_items WHERE name IN (?, ?)",
                    ("Espresso Martini", "Whiskey Sour"),
                )
                .fetchall()
            }

        first_token = self.token_from(
            f"/order/item/{item_ids['Espresso Martini']}"
        )
        with patch("app.send_pushover_order"):
            first_response = self.client.post(
                f"/order/item/{item_ids['Espresso Martini']}",
                data={
                    "csrf_token": first_token,
                    "guest_name": "Noah",
                    "note": "Less ice, please",
                },
            )

        first_cookie = first_response.headers.get("Set-Cookie", "")
        self.assertIn("party_guest_name=Noah", first_cookie)
        self.assertIn("HttpOnly", first_cookie)
        self.assertIn("SameSite=Lax", first_cookie)
        self.assertNotIn("Less ice", first_cookie)

        next_order = self.client.get(f"/order/item/{item_ids['Whiskey Sour']}")
        self.assertIn(b'value="Noah"', next_order.data)
        self.assertNotIn(b"Less ice, please", next_order.data)
        self.assertRegex(next_order.data, rb'<textarea[^>]*>\s*</textarea>')

        second_token = self.token_from(
            f"/order/item/{item_ids['Whiskey Sour']}"
        )
        with patch("app.send_pushover_order"):
            second_response = self.client.post(
                f"/order/item/{item_ids['Whiskey Sour']}",
                data={
                    "csrf_token": second_token,
                    "guest_name": "Mila",
                    "note": "",
                },
            )

        self.assertIn(
            "party_guest_name=Mila",
            second_response.headers.get("Set-Cookie", ""),
        )
        updated_order = self.client.get(
            f"/order/item/{item_ids['Espresso Martini']}"
        )
        self.assertIn(b'value="Mila"', updated_order.data)
        self.assertNotIn(b'value="Noah"', updated_order.data)

    def test_guest_name_is_required_before_sending(self):
        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]

        token = self.token_from(f"/order/item/{item_id}")
        with patch("app.send_pushover_order") as send_order:
            response = self.client.post(
                f"/order/item/{item_id}",
                data={"csrf_token": token, "guest_name": "", "note": "No ice"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter your name before sending the order.", response.data)
        self.assertIn(b"No ice", response.data)
        send_order.assert_not_called()

    def test_guest_cannot_order_unavailable_item(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]
            db.execute("UPDATE menu_items SET available = 0 WHERE id = ?", (item_id,))
            db.commit()

        token = self.token_from("/host/login")
        with patch("app.send_pushover_order") as send_order:
            response = self.client.post(
                f"/order/item/{item_id}",
                data={"csrf_token": token, "guest_name": "Noah", "note": ""},
                follow_redirects=True,
            )

        self.assertIn(b"Espresso Martini is currently out.", response.data)
        self.assertIn(b"Unavailable", response.data)
        send_order.assert_not_called()

    def test_order_cooldown_prevents_accidental_double_tap(self):
        with self.app.app_context():
            from app import get_db

            item_ids = [
                row[0]
                for row in get_db().execute(
                    "SELECT id FROM menu_items WHERE name IN (?, ?) ORDER BY id",
                    ("Espresso Martini", "Whiskey Sour"),
                ).fetchall()
            ]

        token = self.token_from(f"/order/item/{item_ids[0]}")
        with patch("app.send_pushover_order") as send_order:
            first_response = self.client.post(
                f"/order/item/{item_ids[0]}",
                data={"csrf_token": token, "guest_name": "Noah", "note": ""},
                follow_redirects=True,
            )
            second_response = self.client.post(
                f"/order/item/{item_ids[1]}",
                data={"csrf_token": token, "guest_name": "Noah", "note": ""},
                follow_redirects=True,
            )

        self.assertIn(b"Order sent for Noah:", first_response.data)
        self.assertIn(b"Please wait a few seconds", second_response.data)
        self.assertEqual(send_order.call_count, 1)

    def test_order_failure_does_not_expose_provider_details(self):
        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]

        token = self.token_from(f"/order/item/{item_id}")
        response = self.client.post(
            f"/order/item/{item_id}",
            data={"csrf_token": token, "guest_name": "Noah", "note": ""},
            follow_redirects=True,
        )

        self.assertIn(b"The order could not be sent. Please tell the host.", response.data)
        self.assertNotIn(b"Pushover credentials", response.data)

    def test_static_assets_are_cache_busted(self):
        self.login()
        response = self.client.get("/host")
        self.assertRegex(response.text, r'/static/styles\.css\?v=\d+')
        self.assertRegex(response.text, r'/static/js/host\.js\?v=\d+')

    def test_host_can_add_and_disable_item(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "name": "Tom Collins",
                "description": "Gin, lemon, sugar, and soda.",
                "category": "Cocktails",
                "available": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Added Tom Collins", response.data)

        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = ?", ("Tom Collins",)
            ).fetchone()[0]

        token = self.token_from("/host")
        response = self.client.post(
            f"/host/item/{item_id}/toggle",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"is now out", response.data)
        public_response = self.client.get("/")
        self.assertIn(b"Tom Collins", public_response.data)
        self.assertIn(b"Out", public_response.data)

    def test_existing_demo_database_is_migrated_once(self):
        with tempfile.TemporaryDirectory() as data_dir:
            database = sqlite3.connect(f"{data_dir}/menu.db")
            database.execute(
                """
                CREATE TABLE menu_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL,
                    image TEXT NOT NULL DEFAULT '',
                    available INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            database.execute(
                """
                INSERT INTO menu_items
                    (name, description, category, image, available, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Negroni",
                    "Demo item",
                    "Cocktails",
                    "/static/seed/negroni.jpg",
                    1,
                    1,
                ),
            )
            database.execute(
                """
                INSERT INTO menu_items
                    (name, description, category, image, available, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Port",
                    "Existing custom item",
                    "After Dinner",
                    "",
                    1,
                    2,
                ),
            )
            database.commit()
            database.close()

            migrated_app = create_app(
                {
                    "TESTING": True,
                    "SECRET_KEY": "test-secret",
                    "ADMIN_PASSWORD": "party-password",
                    "DATA_DIR": data_dir,
                }
            )
            with migrated_app.app_context():
                from app import get_db

                db = get_db()
                names = {
                    row[0] for row in db.execute("SELECT name FROM menu_items").fetchall()
                }
                version = db.execute(
                    "SELECT value FROM app_meta WHERE key = 'catalog_version'"
                ).fetchone()[0]
                categories = {
                    row[0]
                    for row in db.execute("SELECT name FROM menu_categories").fetchall()
                }

            self.assertNotIn("Negroni", names)
            self.assertIn("Espresso Martini", names)
            self.assertIn("Cola", names)
            self.assertIn("Port", names)
            self.assertIn("After Dinner", categories)
            self.assertEqual(version, "3")

    def test_image_migration_fills_blanks_without_overwriting_custom_images(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            db.execute(
                "UPDATE menu_items SET image = '' WHERE name = 'Espresso Martini'"
            )
            db.execute(
                "UPDATE menu_items SET image = '/uploads/custom.jpg' WHERE name = 'Whiskey Sour'"
            )
            db.execute(
                "UPDATE app_meta SET value = '2' WHERE key = 'catalog_version'"
            )
            db.commit()

        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "ADMIN_PASSWORD": "party-password",
                "DATA_DIR": self.temp_dir.name,
            }
        )

        with self.app.app_context():
            from app import get_db

            db = get_db()
            images = {
                row["name"]: row["image"]
                for row in db.execute(
                    "SELECT name, image FROM menu_items WHERE name IN (?, ?)",
                    ("Espresso Martini", "Whiskey Sour"),
                ).fetchall()
            }
            version = db.execute(
                "SELECT value FROM app_meta WHERE key = 'catalog_version'"
            ).fetchone()[0]

        self.assertEqual(images["Espresso Martini"], "/static/seed/espresso-martini.jpg")
        self.assertEqual(images["Whiskey Sour"], "/uploads/custom.jpg")
        self.assertEqual(version, "3")

    def test_host_can_reorder_items_within_a_category(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            whiskey_sour_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = 'Whiskey Sour'"
            ).fetchone()[0]

        token = self.token_from("/host?category=Cocktails")
        response = self.client.post(
            f"/host/item/{whiskey_sour_id}/move/up",
            data={
                "csrf_token": token,
                "return_to": "/host?category=Cocktails",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Moved Whiskey Sour up", response.data)

        public_response = self.client.get("/")
        self.assertLess(
            public_response.data.index(b"Whiskey Sour"),
            public_response.data.index(b"Espresso Martini"),
        )

    def test_host_can_add_assign_and_reorder_categories(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/category/save",
            data={"csrf_token": token, "name": "Desserts"},
            follow_redirects=True,
        )
        self.assertIn(b"Added category Desserts", response.data)
        self.assertIn(b'<option value="Desserts">Desserts</option>', response.data)
        self.assertIn(b'data-default-category="Desserts"', response.data)

        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "name": "Chocolate Mousse",
                "description": "Dark chocolate and cream.",
                "category": "Desserts",
                "available": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Added Chocolate Mousse", response.data)

        with self.app.app_context():
            from app import get_db

            dessert_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Desserts'"
            ).fetchone()[0]

        token = self.token_from("/host")
        response = self.client.post(
            f"/host/category/{dessert_id}/move/up",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"Moved category Desserts up", response.data)

        public_response = self.client.get("/")
        self.assertIn(b"Chocolate Mousse", public_response.data)
        self.assertLess(
            public_response.data.index(b'href="#category-5">Desserts</a>'),
            public_response.data.index(b'href="#category-6">Snacks</a>'),
        )

    def test_host_can_rename_category_and_existing_items_follow(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            snacks_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Snacks'"
            ).fetchone()[0]

        token = self.token_from("/host")
        response = self.client.post(
            f"/host/category/{snacks_id}/rename",
            data={"csrf_token": token, "name": "Bites"},
            follow_redirects=True,
        )
        self.assertIn(b"Renamed category Snacks to Bites", response.data)
        self.assertIn(b'<option value="Bites">Bites</option>', response.data)
        self.assertIn(b'value="Bites"', response.data)

        with self.app.app_context():
            from app import get_db

            db = get_db()
            renamed_count = db.execute(
                "SELECT COUNT(*) FROM menu_items WHERE category = 'Bites'"
            ).fetchone()[0]
            old_count = db.execute(
                "SELECT COUNT(*) FROM menu_items WHERE category = 'Snacks'"
            ).fetchone()[0]
        self.assertEqual(renamed_count, 6)
        self.assertEqual(old_count, 0)

        public_response = self.client.get("/")
        self.assertIn(b"Bites", public_response.data)
        self.assertIn(b"Jonge Kaasblokjes", public_response.data)

        token = self.token_from("/host")
        response = self.client.post(
            f"/host/category/{snacks_id}/rename",
            data={"csrf_token": token, "name": "Cocktails"},
            follow_redirects=True,
        )
        self.assertIn(b"Category Cocktails already exists", response.data)

    def test_host_can_delete_an_empty_category(self):
        self.login()
        token = self.token_from("/host")
        self.client.post(
            "/host/category/save",
            data={"csrf_token": token, "name": "Desserts"},
            follow_redirects=True,
        )

        with self.app.app_context():
            from app import get_db

            category_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Desserts'"
            ).fetchone()[0]

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category_id}/delete",
            data={"csrf_token": token},
            follow_redirects=True,
        )

        self.assertIn(b"Removed category Desserts", response.data)
        self.assertNotIn(b'value="Desserts"', response.data)
        self.assertNotIn(b"Desserts", self.client.get("/").data)

    def test_host_can_delete_a_category_and_its_items(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            category_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Snacks'"
            ).fetchone()[0]

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category_id}/delete",
            data={"csrf_token": token, "item_action": "delete"},
            follow_redirects=True,
        )

        self.assertIn(b"Removed category Snacks and deleted 6 items", response.data)
        self.assertNotIn(b'value="Snacks"', response.data)
        self.assertNotIn(b"Jonge Kaasblokjes", self.client.get("/").data)

    def test_host_can_keep_removed_category_items_unassigned_and_hidden(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            db = get_db()
            category = db.execute(
                "SELECT id, name FROM menu_categories ORDER BY id LIMIT 1"
            ).fetchone()
            db.execute("DELETE FROM menu_items WHERE category != ?", (category["name"],))
            db.execute("DELETE FROM menu_categories WHERE id != ?", (category["id"],))
            db.commit()

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category['id']}/delete",
            data={"csrf_token": token, "item_action": "unassigned"},
            follow_redirects=True,
        )

        self.assertIn(b"items are now hidden in Unassigned", response.data)
        self.assertIn(b'Unassigned <small class="hidden-category-note">(hidden)</small>', response.data)

        with self.app.app_context():
            from app import get_db

            db = get_db()
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0], 0
            )
            self.assertGreater(
                db.execute(
                    "SELECT COUNT(*) FROM menu_items WHERE category = 'Unassigned'"
                ).fetchone()[0],
                0,
            )

        public_response = self.client.get("/")
        self.assertIn(b"0 items available", public_response.data)
        self.assertNotIn(b"Espresso Martini", public_response.data)
        with self.app.app_context():
            from app import get_db

            hidden_item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE category = 'Unassigned' LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(self.client.get(f"/order/item/{hidden_item_id}").status_code, 404)

        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "ADMIN_PASSWORD": "party-password",
                "DATA_DIR": self.temp_dir.name,
            }
        )
        with self.app.app_context():
            from app import get_db

            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0],
                0,
            )

    def test_host_can_move_removed_category_items_to_existing_category(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            category_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Snacks'"
            ).fetchone()[0]

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category_id}/delete",
            data={
                "csrf_token": token,
                "item_action": "existing",
                "target_category": "Cocktails",
            },
            follow_redirects=True,
        )

        self.assertIn(b"moved its items to Cocktails", response.data)
        with self.app.app_context():
            from app import get_db

            db = get_db()
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM menu_items WHERE category = 'Cocktails'"
                ).fetchone()[0],
                15,
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM menu_categories WHERE name = 'Snacks'"
                ).fetchone()[0],
                0,
            )

        public_response = self.client.get("/")
        self.assertNotIn(b'href="#category-5">Snacks</a>', public_response.data)
        self.assertIn(b"Jonge Kaasblokjes", public_response.data)

    def test_host_can_move_removed_category_items_to_new_category(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            category_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Hard Drinks'"
            ).fetchone()[0]

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category_id}/delete",
            data={
                "csrf_token": token,
                "item_action": "new",
                "new_category": "Spirits",
            },
            follow_redirects=True,
        )

        self.assertIn(b"moved its items to Spirits", response.data)
        self.assertIn(b'value="Spirits"', response.data)
        with self.app.app_context():
            from app import get_db

            db = get_db()
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM menu_items WHERE category = 'Spirits'"
                ).fetchone()[0],
                4,
            )
        self.assertIn(b"Spirits", self.client.get("/").data)

    def test_removing_populated_category_requires_an_item_action(self):
        self.login()
        with self.app.app_context():
            from app import get_db

            category_id = get_db().execute(
                "SELECT id FROM menu_categories WHERE name = 'Snacks'"
            ).fetchone()[0]

        token = self.token_from("/host?manage_categories=1")
        response = self.client.post(
            f"/host/category/{category_id}/delete",
            data={"csrf_token": token},
            follow_redirects=True,
        )

        self.assertIn(b"Choose what should happen", response.data)
        self.assertIn(b'value="Snacks"', response.data)

    def test_category_names_are_unique_case_insensitively(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/category/save",
            data={"csrf_token": token, "name": "cocktails"},
            follow_redirects=True,
        )
        self.assertIn(b"Category Cocktails already exists", response.data)

        with self.app.app_context():
            from app import get_db

            count = get_db().execute(
                "SELECT COUNT(*) FROM menu_categories WHERE name = ? COLLATE NOCASE",
                ("cocktails",),
            ).fetchone()[0]
        self.assertEqual(count, 1)

        token = self.token_from("/host")
        response = self.client.post(
            "/host/category/save",
            data={"csrf_token": token, "name": "Unassigned"},
            follow_redirects=True,
        )
        self.assertIn(b"Unassigned is reserved for hidden items", response.data)

    def test_bulk_csv_import(self):
        self.login()
        token = self.token_from("/host")
        csv_data = (
            "name,description,category,available,image_url,image_filename\n"
            "Popcorn,Butter and sea salt,Snacks,yes,,\n"
            "Invalid row,Missing category,,yes,,\n"
        ).encode()
        response = self.client.post(
            "/host/bulk-import",
            data={
                "csrf_token": token,
                "bulk_file": (io.BytesIO(csv_data), "menu.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Imported 1 item", response.data)
        self.assertIn(b"Skipped 1 invalid row", response.data)
        self.assertIn(b"Popcorn", self.client.get("/").data)

    def test_host_can_export_and_restore_the_complete_menu(self):
        self.login()
        custom_image = Path(self.app.config["UPLOAD_DIR"]) / "rollback-photo.jpg"
        custom_image.write_bytes(b"portable menu image")

        with self.app.app_context():
            from app import get_db

            db = get_db()
            category_order = (
                "Snacks",
                "Cocktails",
                "Booze, Beer & Wine",
                "Hard Drinks",
                "Soft Drinks",
            )
            for position, category in enumerate(category_order, start=1):
                db.execute(
                    "UPDATE menu_categories SET sort_order = ? WHERE name = ?",
                    (position, category),
                )
            db.execute(
                "INSERT INTO menu_categories (name, sort_order) VALUES (?, ?)",
                ("Desserts", 6),
            )
            db.execute(
                """
                UPDATE menu_items
                SET description = ?, available = 0, image = ?, sort_order = 1
                WHERE name = 'Whiskey Sour'
                """,
                ("Rollback recipe", "/uploads/rollback-photo.jpg"),
            )
            db.execute(
                "UPDATE menu_items SET sort_order = 2 WHERE name = 'Espresso Martini'"
            )
            db.execute(
                "UPDATE menu_items SET category = ?, sort_order = 1 WHERE name = 'Fanta'",
                ("Unassigned",),
            )
            db.execute(
                "UPDATE menu_items SET image = ? WHERE name = 'Cola'",
                ("https://example.com/cola.jpg",),
            )
            db.commit()

        export_response = self.client.get("/host/export.zip")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(
            "attachment; filename=party-menu-export-",
            export_response.headers["Content-Disposition"],
        )
        export_payload = export_response.data

        with zipfile.ZipFile(io.BytesIO(export_payload)) as archive:
            archive_names = set(archive.namelist())
            self.assertIn("menu.csv", archive_names)
            self.assertIn("categories.csv", archive_names)
            self.assertIn("manifest.json", archive_names)
            categories = list(
                csv.DictReader(io.StringIO(archive.read("categories.csv").decode()))
            )
            self.assertEqual(
                [row["name"] for row in categories],
                [*category_order, "Desserts"],
            )
            menu_rows = list(
                csv.DictReader(io.StringIO(archive.read("menu.csv").decode()))
            )
            whiskey = next(row for row in menu_rows if row["name"] == "Whiskey Sour")
            fanta = next(row for row in menu_rows if row["name"] == "Fanta")
            self.assertEqual(whiskey["available"], "no")
            self.assertEqual(whiskey["sort_order"], "1")
            self.assertTrue(whiskey["image_filename"].startswith("images/"))
            self.assertIn(whiskey["image_filename"], archive_names)
            self.assertEqual(fanta["category"], "Unassigned")

        with self.app.app_context():
            from app import get_db

            db = get_db()
            db.execute("DELETE FROM menu_items")
            db.execute("DELETE FROM menu_categories")
            db.execute(
                "INSERT INTO menu_categories (name, sort_order) VALUES ('Temporary', 1)"
            )
            db.execute(
                """
                INSERT INTO menu_items
                    (name, description, category, image, available, sort_order)
                VALUES ('Temporary item', '', 'Temporary', '', 1, 1)
                """
            )
            db.commit()

        token = self.token_from("/host")
        restore_response = self.client.post(
            "/host/bulk-import",
            data={
                "csrf_token": token,
                "import_mode": "replace",
                "bulk_file": (io.BytesIO(export_payload), "party-menu-export.zip"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Restored the menu from the archive with 25 item(s)", restore_response.data)

        with self.app.app_context():
            from app import get_db

            db = get_db()
            restored_categories = [
                row["name"]
                for row in db.execute(
                    "SELECT name FROM menu_categories ORDER BY sort_order, id"
                ).fetchall()
            ]
            self.assertEqual(restored_categories, [*category_order, "Desserts"])
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0], 25
            )
            whiskey = db.execute(
                """
                SELECT description, category, image, available, sort_order
                FROM menu_items WHERE name = 'Whiskey Sour'
                """
            ).fetchone()
            self.assertEqual(whiskey["description"], "Rollback recipe")
            self.assertEqual(whiskey["category"], "Cocktails")
            self.assertEqual(whiskey["available"], 0)
            self.assertEqual(whiskey["sort_order"], 1)
            self.assertTrue(whiskey["image"].startswith("/uploads/"))
            restored_image = Path(self.app.config["UPLOAD_DIR"]) / Path(
                whiskey["image"]
            ).name
            self.assertEqual(restored_image.read_bytes(), b"portable menu image")
            self.assertEqual(
                db.execute(
                    "SELECT category FROM menu_items WHERE name = 'Fanta'"
                ).fetchone()[0],
                "Unassigned",
            )
            self.assertEqual(
                db.execute(
                    "SELECT image FROM menu_items WHERE name = 'Cola'"
                ).fetchone()[0],
                "https://example.com/cola.jpg",
            )

        public_menu = self.client.get("/").data
        self.assertNotIn(b"Fanta", public_menu)
        self.assertNotIn(b"Temporary item", public_menu)

    def test_invalid_replace_import_does_not_delete_the_current_menu(self):
        self.login()
        archive_payload = io.BytesIO()
        with zipfile.ZipFile(archive_payload, "w") as archive:
            archive.writestr(
                "menu.csv",
                "name,category,available\nInvalid item,Missing category,yes\n",
            )
            archive.writestr(
                "categories.csv",
                "name,sort_order\nCocktails,1\n",
            )
        archive_payload.seek(0)

        token = self.token_from("/host")
        response = self.client.post(
            "/host/bulk-import",
            data={
                "csrf_token": token,
                "import_mode": "replace",
                "bulk_file": (archive_payload, "invalid-export.zip"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Import failed: Unknown category Missing category", response.data)

        with self.app.app_context():
            from app import get_db

            db = get_db()
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0], 25
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM menu_categories").fetchone()[0], 5
            )

    def test_post_without_csrf_is_rejected(self):
        response = self.client.post("/host/login", data={"password": "party-password"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
