import io
import re
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
        self.assertIn(b"Negroni", response.data)
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})

    def test_host_can_add_and_disable_item(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "name": "Espresso Martini",
                "description": "Vodka, espresso, and coffee liqueur.",
                "category": "Cocktails",
                "available": "1",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Added Espresso Martini", response.data)

        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = ?", ("Espresso Martini",)
            ).fetchone()[0]

        token = self.token_from("/host")
        response = self.client.post(
            f"/host/item/{item_id}/toggle",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"is now out", response.data)
        public_response = self.client.get("/")
        self.assertIn(b"Espresso Martini", public_response.data)
        self.assertIn(b"Out", public_response.data)

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
