import io
import re
import sqlite3
import tempfile
import unittest

from app import create_app


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
        image_paths = re.findall(rb'<img src="([^"]+)"', response.data)
        self.assertEqual(len(image_paths), 25)
        for image_path in image_paths:
            image_response = self.client.get(image_path.decode())
            self.assertEqual(image_response.status_code, 200)
            image_response.close()
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})

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

    def test_post_without_csrf_is_rejected(self):
        response = self.client.post("/host/login", data={"password": "party-password"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
