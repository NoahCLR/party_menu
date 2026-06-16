import csv
import io
import json
import re
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from PIL import Image

from app import create_app, send_pushover_basket_order, send_pushover_order


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

    def image_bytes(self, image_format="PNG", size=(320, 240), color=(20, 80, 160)):
        payload = io.BytesIO()
        Image.new("RGB", size, color).save(payload, format=image_format)
        return payload.getvalue()

    def test_public_menu_and_health(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tonight's Menu", response.data)
        self.assertIn(b"Espresso Martini", response.data)
        self.assertIn(b"Hard Drinks", response.data)
        self.assertIn(b"Soft Drinks", response.data)
        self.assertIn(b"25 items available", response.data)
        self.assertEqual(response.data.count(b'class="menu-order-button"'), 25)
        self.assertEqual(response.data.count(b'data-basket-add="'), 25)
        self.assertIn(b'aria-label="Order Espresso Martini"', response.data)
        self.assertIn(b'aria-label="Add Espresso Martini to basket"', response.data)
        self.assertIn(b'id="basket-summary"', response.data)
        self.assertIn(b'id="menu-search-input"', response.data)
        self.assertIn(b"Search names and descriptions", response.data)
        self.assertIn(b'aria-label="Clear search"', response.data)
        self.assertRegex(response.data, rb'/static/js/menu\.js\?v=\d+')
        self.assertRegex(response.data, rb'/static/js/basket-store\.js\?v=\d+')
        self.assertRegex(response.data, rb'/static/js/flashes\.js\?v=\d+')
        self.assertEqual(response.data.count(b'data-focus-x="50.0"'), 25)
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
                "Espresso Martini",
                "Cocktails",
                "Noah",
                "Less ice, please",
                [
                    {"name": "Vodka", "ml": "40"},
                    {"name": "Espresso", "ml": "30"},
                    {"name": "Ice", "ml": ""},
                ],
            )

        pushover_request = mocked.call_args.args[0]
        payload = parse_qs(pushover_request.data.decode())
        self.assertEqual(payload["token"], ["application-token"])
        self.assertEqual(payload["user"], ["user-key"])
        self.assertEqual(payload["title"], ["Order from Noah"])
        self.assertEqual(
            payload["message"],
            [
                "Item: Espresso Martini\nCategory: Cocktails\nNote: Less ice, please"
                "\n\nRecipe:\nEspresso Martini\n- 40 ml Vodka\n- 30 ml Espresso\n- Ice"
            ],
        )
        self.assertEqual(mocked.call_args.kwargs["timeout"], 5)

    def test_pushover_basket_order_payload(self):
        self.app.config.update(
            PUSHOVER_API_TOKEN="application-token",
            PUSHOVER_USER_KEY="user-key",
        )
        response = io.BytesIO(b'{"status": 1}')

        with self.app.app_context(), patch("app.urlopen", return_value=response) as mocked:
            send_pushover_basket_order(
                [
                    {
                        "name": "Moscow Mule",
                        "quantity": 2,
                        "recipe": [
                            {"name": "Vodka", "ml": "50"},
                            {"name": "Ginger beer", "ml": "120"},
                            {"name": "Lime wedge", "ml": ""},
                        ],
                    },
                    {
                        "name": "Gin & Tonic",
                        "quantity": 1,
                        "recipe": [
                            {"name": "Gin", "ml": "50"},
                            {"name": "Tonic", "ml": "150"},
                        ],
                    },
                ],
                "Noah",
                "Bring together",
            )

        payload = parse_qs(mocked.call_args.args[0].data.decode())
        self.assertEqual(payload["title"], ["Order from Noah"])
        self.assertEqual(
            payload["message"],
            [
                "Items:\n2x Moscow Mule\n1x Gin & Tonic\nNote: Bring together"
                "\n\nRecipes:\nMoscow Mule\n- 50 ml Vodka\n- 120 ml Ginger beer"
                "\n- Lime wedge\n\nGin & Tonic\n- 50 ml Gin\n- 150 ml Tonic"
            ],
        )

    def test_guest_can_order_available_item(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps(
                        [
                            {"name": "Vodka", "ml": "40"},
                            {"name": "Ice", "ml": ""},
                        ]
                    ),
                    item_id,
                ),
            )
            db.commit()

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
            "Espresso Martini",
            "Cocktails",
            "Noah",
            "Less ice, please",
            [
                {"name": "Vodka", "ml": "40"},
                {"name": "Ice", "ml": ""},
            ],
        )

    def test_recipes_are_only_exposed_to_the_host(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps(
                        [{"name": "Private test ingredient", "ml": "42"}]
                    ),
                    item_id,
                ),
            )
            db.commit()

        self.assertNotIn(b"Private test ingredient", self.client.get("/").data)
        self.assertNotIn(
            b"Private test ingredient",
            self.client.get(f"/order/item/{item_id}").data,
        )
        self.assertNotIn(
            b"Private test ingredient", self.client.get("/order/basket").data
        )

        self.login()
        self.assertIn(b"Private test ingredient", self.client.get("/host").data)

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

        basket_order = self.client.get("/order/basket")
        self.assertIn(b'value="Noah"', basket_order.data)
        self.assertNotIn(b"Less ice, please", basket_order.data)

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

    def test_guest_can_send_a_combined_basket_order(self):
        with self.app.app_context():
            from app import get_db

            item_ids = {
                row["name"]: row["id"]
                for row in get_db()
                .execute(
                    "SELECT id, name FROM menu_items WHERE name IN (?, ?)",
                    ("Moscow Mule", "Garlic Olives"),
                )
                .fetchall()
            }
            db = get_db()
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps(
                        [
                            {"name": "Vodka", "ml": "50", "abv": "40"},
                            {"name": "Ginger beer", "ml": "120"},
                        ]
                    ),
                    item_ids["Moscow Mule"],
                ),
            )
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps([{"name": "Cocktail pick", "ml": ""}]),
                    item_ids["Garlic Olives"],
                ),
            )
            db.commit()

        token = self.token_from("/order/basket")
        basket = [
            {"id": item_ids["Moscow Mule"], "quantity": 2},
            {"id": item_ids["Garlic Olives"], "quantity": 1},
        ]
        with patch("app.send_pushover_basket_order") as send_order:
            response = self.client.post(
                "/order/basket",
                data={
                    "csrf_token": token,
                    "basket_items": json.dumps(basket),
                    "guest_name": "Noah",
                    "note": "Bring together",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/?basket_sent=1"))
        self.assertIn("party_guest_name=Noah", response.headers.get("Set-Cookie", ""))
        send_order.assert_called_once()
        sent_items, guest_name, note = send_order.call_args.args
        self.assertEqual(
            [(item["name"], item["quantity"]) for item in sent_items],
            [("Moscow Mule", 2), ("Garlic Olives", 1)],
        )
        self.assertEqual(
            sent_items[0]["recipe"],
            [
                {"name": "Vodka", "ml": "50", "abv": "40"},
                {"name": "Ginger beer", "ml": "120"},
            ],
        )
        self.assertEqual(
            sent_items[1]["recipe"],
            [{"name": "Cocktail pick", "ml": ""}],
        )
        self.assertEqual(guest_name, "Noah")
        self.assertEqual(note, "Bring together")

        with self.app.app_context():
            from app import get_db

            db = get_db()
            order = db.execute(
                "SELECT * FROM orders WHERE guest_name = 'Noah'"
            ).fetchone()
            self.assertEqual(order["source"], "basket")
            self.assertEqual(order["status"], "new")
            self.assertEqual(order["item_count"], 3)
            self.assertAlmostEqual(order["total_alcohol_grams"], 31.56)
            saved_items = db.execute(
                """
                SELECT name, quantity, recipient_name, recipe, alcohol_grams
                FROM order_items
                WHERE order_id = ?
                ORDER BY id
                """,
                (order["id"],),
            ).fetchall()
            self.assertEqual(
                [
                    (item["name"], item["quantity"], item["recipient_name"])
                    for item in saved_items
                ],
                [("Moscow Mule", 2, "Noah"), ("Garlic Olives", 1, "Noah")],
            )
            self.assertEqual(
                json.loads(saved_items[0]["recipe"])[0],
                {"name": "Vodka", "ml": "50", "abv": "40"},
            )
            self.assertAlmostEqual(saved_items[0]["alcohol_grams"], 31.56)

    def test_basket_checkout_rejects_an_item_that_is_no_longer_available(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Moscow Mule'"
            ).fetchone()[0]

        token = self.token_from("/order/basket")
        with self.app.app_context():
            from app import get_db

            db = get_db()
            db.execute("UPDATE menu_items SET available = 0 WHERE id = ?", (item_id,))
            db.commit()

        with patch("app.send_pushover_basket_order") as send_order:
            response = self.client.post(
                "/order/basket",
                data={
                    "csrf_token": token,
                    "basket_items": json.dumps([{"id": item_id, "quantity": 1}]),
                    "guest_name": "Noah",
                    "note": "",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"no longer available", response.data)
        send_order.assert_not_called()

    def test_basket_recipients_can_be_split_and_host_can_delete_names(self):
        self.app.config["ORDER_COOLDOWN_SECONDS"] = 0
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Moscow Mule'"
            ).fetchone()[0]
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps(
                        [
                            {"name": "Vodka", "ml": "50", "abv": "40"},
                            {"name": "Ginger beer", "ml": "120"},
                        ]
                    ),
                    item_id,
                ),
            )
            db.commit()

        token = self.token_from("/order/basket")
        basket = [
            {"id": item_id, "quantity": 2, "recipients": ["Noah", "Mila"]},
        ]
        with patch("app.send_pushover_basket_order"):
            response = self.client.post(
                "/order/basket",
                data={
                    "csrf_token": token,
                    "basket_items": json.dumps(basket),
                    "guest_name": "Noah",
                    "note": "For the table",
                },
            )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            from app import get_db

            rows = get_db().execute(
                """
                SELECT name, quantity, recipient_name, alcohol_grams
                FROM order_items
                ORDER BY recipient_name
                """
            ).fetchall()
            self.assertEqual(
                [(row["name"], row["quantity"], row["recipient_name"]) for row in rows],
                [("Moscow Mule", 1, "Mila"), ("Moscow Mule", 1, "Noah")],
            )
            self.assertAlmostEqual(rows[0]["alcohol_grams"], 15.78)

        basket_page = self.client.get("/order/basket")
        self.assertIn(b"guest-names-data", basket_page.data)
        self.assertIn(b"Mila", basket_page.data)
        self.assertIn(b"name-suggestions.js", basket_page.data)

        self.login()
        queue_json = self.client.get("/host/orders.json").json
        recipients = {
            item["recipient_name"] for item in queue_json["orders"][0]["items"]
        }
        self.assertEqual(recipients, {"Mila", "Noah"})

        stats = self.client.get("/host/stats.json").json["stats"]
        self.assertEqual(
            [(guest["guest_name"], guest["items"]) for guest in stats["guests"]],
            [("Mila", 1), ("Noah", 1)],
        )

        names_page = self.client.get("/host/names")
        self.assertIn(b"Guest names", names_page.data)
        self.assertIn(b"Mila", names_page.data)
        self.assertNotIn(b"built-in method", names_page.data)
        delete_match = re.search(rb'/host/names/(\d+)/delete', names_page.data)
        self.assertIsNotNone(delete_match)
        delete_token = self.token_from("/host/names")
        delete_response = self.client.post(
            delete_match.group(0).decode(),
            data={"csrf_token": delete_token},
            follow_redirects=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertNotIn(b"<strong>Mila</strong>", delete_response.data)

        queue_after_delete = self.client.get("/host/orders.json").json
        deleted_recipients = {
            item["recipient_name"] for item in queue_after_delete["orders"][0]["items"]
        }
        self.assertEqual(deleted_recipients, {"Noah", "Unassigned"})
        stats_after_delete = self.client.get("/host/stats.json").json["stats"]
        self.assertEqual(
            [(guest["guest_name"], guest["items"]) for guest in stats_after_delete["guests"]],
            [("Noah", 1), ("Unassigned", 1)],
        )

    def test_basket_checkout_rejects_invalid_quantities(self):
        with self.app.app_context():
            from app import get_db

            item_id = get_db().execute(
                "SELECT id FROM menu_items WHERE name = 'Moscow Mule'"
            ).fetchone()[0]

        token = self.token_from("/order/basket")
        with patch("app.send_pushover_basket_order") as send_order:
            response = self.client.post(
                "/order/basket",
                data={
                    "csrf_token": token,
                    "basket_items": json.dumps([{"id": item_id, "quantity": 21}]),
                    "guest_name": "Noah",
                    "note": "",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"invalid quantity", response.data)
        send_order.assert_not_called()

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

        self.assertIn(b"Order received for Noah: Espresso Martini.", response.data)
        self.assertIn(b"host notification failed", response.data)
        self.assertNotIn(b"Pushover credentials", response.data)
        with self.app.app_context():
            from app import get_db

            saved = get_db().execute(
                "SELECT COUNT(*) FROM orders WHERE guest_name = 'Noah'"
            ).fetchone()[0]
            self.assertEqual(saved, 1)

    def test_host_can_manage_order_queue_and_stats(self):
        with self.app.app_context():
            from app import get_db

            db = get_db()
            item_id = db.execute(
                "SELECT id FROM menu_items WHERE name = 'Espresso Martini'"
            ).fetchone()[0]
            db.execute(
                "UPDATE menu_items SET recipe = ? WHERE id = ?",
                (
                    json.dumps(
                        [
                            {"name": "Vodka", "ml": "40", "abv": "40"},
                            {"name": "Espresso", "ml": "30"},
                        ]
                    ),
                    item_id,
                ),
            )
            db.commit()

        token = self.token_from(f"/order/item/{item_id}")
        with patch("app.send_pushover_order"):
            response = self.client.post(
                f"/order/item/{item_id}",
                data={"csrf_token": token, "guest_name": "Mila", "note": "Fast"},
                follow_redirects=True,
            )
        self.assertIn(b"Order sent for Mila: Espresso Martini.", response.data)

        self.login()
        queue_page = self.client.get("/host/orders")
        self.assertIn(b"Order queue", queue_page.data)
        self.assertIn(b"host-orders.js", queue_page.data)
        self.assertIn(b"Espresso Martini", queue_page.data)
        self.assertIn(b'"abv": "40"', queue_page.data)

        queue_json = self.client.get("/host/orders.json").json
        self.assertEqual(queue_json["summary"]["active_orders"], 1)
        self.assertEqual(queue_json["orders"][0]["guest_name"], "Mila")
        self.assertEqual(queue_json["orders"][0]["items"][0]["recipient_name"], "Mila")
        self.assertAlmostEqual(queue_json["orders"][0]["total_alcohol_grams"], 12.62)

        stats_page = self.client.get("/host/stats")
        self.assertIn(b"Party stats", stats_page.data)
        self.assertIn(b"host-stats.js", stats_page.data)
        self.assertIn(b'id="highlight-stats"', stats_page.data)
        self.assertIn(b'id="timeline-graph"', stats_page.data)
        self.assertIn(b'id="category-stats"', stats_page.data)
        stats_json = self.client.get("/host/stats.json").json["stats"]
        self.assertEqual(stats_json["summary"]["total_orders"], 1)
        self.assertEqual(stats_json["guests"][0]["guest_name"], "Mila")
        self.assertAlmostEqual(stats_json["guests"][0]["standard_drinks"], 1.26)
        self.assertEqual(stats_json["highlights"]["unique_guests"], 1)
        self.assertEqual(stats_json["highlights"]["top_guest"]["guest_name"], "Mila")
        self.assertEqual(stats_json["highlights"]["top_item"]["name"], "Espresso Martini")
        self.assertEqual(stats_json["highlights"]["top_category"]["category"], "Cocktails")
        self.assertEqual(stats_json["highlights"]["biggest_order"]["item_count"], 1)
        self.assertAlmostEqual(stats_json["highlights"]["avg_items_per_order"], 1.0)
        self.assertAlmostEqual(stats_json["highlights"]["completion_rate"], 0.0)
        self.assertEqual(stats_json["categories"][0]["category"], "Cocktails")
        self.assertEqual(stats_json["timeline"][0]["items"], 1)

        host_token = self.token_from("/host/orders")
        order_id = queue_json["orders"][0]["id"]
        complete = self.client.post(
            f"/host/orders/{order_id}/complete",
            headers={"X-CSRF-Token": host_token},
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(self.client.get("/host/orders.json").json["orders"], [])
        self.assertAlmostEqual(
            self.client.get("/host/stats.json").json["stats"]["highlights"]["completion_rate"],
            100.0,
        )
        completed = self.client.get("/host/orders.json?status=completed").json
        self.assertEqual(completed["orders"][0]["status"], "completed")

        clear = self.client.post(
            "/host/orders/clear",
            data={"csrf_token": host_token, "action": "completed"},
        )
        self.assertEqual(clear.status_code, 200)
        self.assertEqual(clear.json["cleared"], 1)
        self.assertEqual(self.client.get("/host/stats.json").json["stats"]["summary"]["total_orders"], 0)


    def test_static_assets_are_cache_busted(self):
        self.login()
        response = self.client.get("/host")
        self.assertRegex(response.text, r'/static/styles\.css\?v=\d+')
        self.assertRegex(response.text, r'/static/js/host\.js\?v=\d+')
        self.assertIn(b'id="host-search-input"', response.data)
        self.assertIn(b"Search name, description, category, or recipe", response.data)
        self.assertIn(b"data-host-row", response.data)
        self.assertIn(b'id="host-search-empty"', response.data)

        stylesheet_response = self.client.get("/static/styles.css")
        stylesheet = stylesheet_response.text
        stylesheet_response.close()
        self.assertIn(".host-search {", stylesheet)
        self.assertIn("[data-host-row][hidden]", stylesheet)
        self.assertIn('body input:not([type="hidden"])', stylesheet)
        self.assertIn("body select,", stylesheet)
        self.assertIn("body textarea {\n    font-size: 16px;", stylesheet)
        self.assertIn(".category-row-actions .order-controls {\n    display: flex;", stylesheet)
        self.assertIn("grid-template-columns: auto minmax(0, 1fr) auto;", stylesheet)
        self.assertIn(".menu-item:not(.no-image) {", stylesheet)
        self.assertIn("height: clamp(250px, 55vw, 300px);", stylesheet)
        self.assertIn(".image-focus-preview {", stylesheet)
        self.assertIn(".public-flash.is-dismissing,", stylesheet)

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

    def test_host_can_add_and_edit_a_structured_recipe(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "name": "Test Cocktail",
                "description": "A test drink.",
                "category": "Cocktails",
                "available": "1",
                "recipe_name": ["Rum", "Lime juice", "Ice"],
                "recipe_ml": ["50", "22.50", ""],
            },
            follow_redirects=True,
        )
        self.assertIn(b"Added Test Cocktail", response.data)
        self.assertIn(b'id="image-focus-preview"', response.data)
        self.assertIn(b'"name": "Rum"', response.data)
        self.assertIn(b'"ml": "22.5"', response.data)

        with self.app.app_context():
            from app import get_db

            row = get_db().execute(
                "SELECT id, recipe FROM menu_items WHERE name = 'Test Cocktail'"
            ).fetchone()
            item_id = row["id"]
            self.assertEqual(
                json.loads(row["recipe"]),
                [
                    {"name": "Rum", "ml": "50"},
                    {"name": "Lime juice", "ml": "22.5"},
                    {"name": "Ice", "ml": ""},
                ],
            )

        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "item_id": str(item_id),
                "name": "Test Cocktail",
                "description": "A test drink.",
                "category": "Cocktails",
                "available": "1",
                "recipe_name": ["Rum", "Orange peel"],
                "recipe_ml": ["60", ""],
            },
            follow_redirects=True,
        )
        self.assertIn(b"Updated Test Cocktail", response.data)
        with self.app.app_context():
            from app import get_db

            recipe = get_db().execute(
                "SELECT recipe FROM menu_items WHERE id = ?", (item_id,)
            ).fetchone()[0]
        self.assertEqual(
            json.loads(recipe),
            [
                {"name": "Rum", "ml": "60"},
                {"name": "Orange peel", "ml": ""},
            ],
        )

    def test_uploaded_images_are_optimized_to_webp_with_a_focus_point(self):
        self.login()
        token = self.token_from("/host")
        response = self.client.post(
            "/host/item/save",
            data={
                "csrf_token": token,
                "name": "Focused Cocktail",
                "description": "Image optimization test.",
                "category": "Cocktails",
                "available": "1",
                "image_focus_x": "18.5",
                "image_focus_y": "77",
                "image_file": (
                    io.BytesIO(self.image_bytes(size=(2400, 1200))),
                    "large-cocktail.png",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Added Focused Cocktail", response.data)

        with self.app.app_context():
            from app import get_db

            item = get_db().execute(
                """
                SELECT image, image_focus_x, image_focus_y
                FROM menu_items WHERE name = 'Focused Cocktail'
                """
            ).fetchone()

        self.assertTrue(item["image"].endswith(".webp"))
        self.assertEqual(item["image_focus_x"], 18.5)
        self.assertEqual(item["image_focus_y"], 77)
        stored_path = Path(self.app.config["UPLOAD_DIR"]) / Path(item["image"]).name
        with Image.open(stored_path) as optimized:
            self.assertEqual(optimized.format, "WEBP")
            self.assertLessEqual(max(optimized.size), 1600)
            self.assertEqual(optimized.size, (1600, 800))

        public_menu = self.client.get("/").data
        self.assertIn(b'data-focus-x="18.5"', public_menu)
        self.assertIn(b'data-focus-y="77.0"', public_menu)

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
                port_recipe = db.execute(
                    "SELECT recipe FROM menu_items WHERE name = 'Port'"
                ).fetchone()[0]
                port_focus = db.execute(
                    """
                    SELECT image_focus_x, image_focus_y
                    FROM menu_items WHERE name = 'Port'
                    """
                ).fetchone()

            self.assertNotIn("Negroni", names)
            self.assertIn("Espresso Martini", names)
            self.assertIn("Cola", names)
            self.assertIn("Port", names)
            self.assertIn("After Dinner", categories)
            self.assertEqual(port_recipe, "[]")
            self.assertEqual(tuple(port_focus), (50, 50))
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
        csv_content = io.StringIO()
        writer = csv.DictWriter(
            csv_content,
            fieldnames=(
                "name",
                "description",
                "category",
                "available",
                "image_url",
                "image_filename",
                "image_focus_x",
                "image_focus_y",
                "recipe",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Popcorn",
                "description": "Butter and sea salt",
                "category": "Snacks",
                "available": "yes",
                "image_focus_x": "25",
                "image_focus_y": "75",
                "recipe": json.dumps(
                    [
                        {"name": "Butter", "ml": "15"},
                        {"name": "Sea salt", "ml": ""},
                    ]
                ),
            }
        )
        writer.writerow(
            {
                "name": "Invalid row",
                "description": "Missing category",
                "category": "",
                "available": "yes",
                "recipe": "[]",
            }
        )
        csv_data = csv_content.getvalue().encode()
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
        with self.app.app_context():
            from app import get_db

            item = get_db().execute(
                """
                SELECT recipe, image_focus_x, image_focus_y
                FROM menu_items WHERE name = 'Popcorn'
                """
            ).fetchone()
        self.assertEqual(
            json.loads(item["recipe"]),
            [
                {"name": "Butter", "ml": "15"},
                {"name": "Sea salt", "ml": ""},
            ],
        )
        self.assertEqual(item["image_focus_x"], 25)
        self.assertEqual(item["image_focus_y"], 75)

    def test_bulk_zip_import_creates_categories_and_optimizes_images(self):
        self.login()
        csv_content = io.StringIO()
        writer = csv.DictWriter(
            csv_content,
            fieldnames=(
                "name",
                "description",
                "category",
                "available",
                "image_filename",
                "image_focus_x",
                "image_focus_y",
                "category_order",
                "sort_order",
                "recipe",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Brownie",
                "description": "Chocolate brownie",
                "category": "Desserts",
                "available": "yes",
                "image_filename": "images/brownie.png",
                "image_focus_x": "20",
                "image_focus_y": "80",
                "category_order": "1",
                "sort_order": "2",
                "recipe": "[]",
            }
        )
        writer.writerow(
            {
                "name": "Tiramisu",
                "description": "Coffee dessert",
                "category": "Desserts",
                "available": "yes",
                "category_order": "1",
                "sort_order": "1",
                "recipe": "[]",
            }
        )
        writer.writerow(
            {
                "name": "Missing photo",
                "category": "Late Snacks",
                "available": "yes",
                "image_filename": "images/missing.png",
                "category_order": "2",
                "sort_order": "1",
                "recipe": "[]",
            }
        )
        writer.writerow(
            {
                "name": "Corrupt photo",
                "category": "Late Snacks",
                "available": "yes",
                "image_filename": "images/corrupt.png",
                "category_order": "2",
                "sort_order": "2",
                "recipe": "[]",
            }
        )

        archive_payload = io.BytesIO()
        with zipfile.ZipFile(archive_payload, "w") as archive:
            archive.writestr("menu.csv", csv_content.getvalue())
            archive.writestr(
                "images/brownie.png",
                self.image_bytes(size=(2400, 1200), color=(80, 40, 20)),
            )
            archive.writestr("images/corrupt.png", b"not an image")
        archive_payload.seek(0)

        token = self.token_from("/host")
        response = self.client.post(
            "/host/bulk-import",
            data={
                "csrf_token": token,
                "bulk_file": (archive_payload, "desserts.zip"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Imported 2 item(s). Skipped 2 invalid row(s).", response.data)

        with self.app.app_context():
            from app import get_db

            db = get_db()
            dessert_items = db.execute(
                """
                SELECT name, image, image_focus_x, image_focus_y
                FROM menu_items WHERE category = 'Desserts'
                ORDER BY sort_order, id
                """
            ).fetchall()
            categories = [
                row["name"]
                for row in db.execute(
                    "SELECT name FROM menu_categories ORDER BY sort_order, id"
                ).fetchall()
            ]

        self.assertEqual(
            [item["name"] for item in dessert_items], ["Tiramisu", "Brownie"]
        )
        self.assertEqual(categories[-1], "Desserts")
        self.assertNotIn("Late Snacks", categories)
        brownie = dessert_items[1]
        self.assertEqual(brownie["image_focus_x"], 20)
        self.assertEqual(brownie["image_focus_y"], 80)
        self.assertTrue(brownie["image"].endswith(".webp"))
        with Image.open(
            Path(self.app.config["UPLOAD_DIR"]) / Path(brownie["image"]).name
        ) as optimized:
            self.assertEqual(optimized.format, "WEBP")
            self.assertEqual(optimized.size, (1600, 800))
        self.assertEqual(len(list(Path(self.app.config["UPLOAD_DIR"]).iterdir())), 1)

    def test_host_can_export_and_restore_the_complete_menu(self):
        self.login()
        custom_image = Path(self.app.config["UPLOAD_DIR"]) / "rollback-photo.jpg"
        custom_image.write_bytes(
            self.image_bytes(image_format="JPEG", size=(640, 480), color=(90, 30, 10))
        )

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
                SET description = ?, available = 0, image = ?, sort_order = 1,
                    recipe = ?, image_focus_x = 30, image_focus_y = 82
                WHERE name = 'Whiskey Sour'
                """,
                (
                    "Rollback recipe",
                    "/uploads/rollback-photo.jpg",
                    json.dumps(
                        [
                            {"name": "Whiskey", "ml": "60"},
                            {"name": "Lemon juice", "ml": "30"},
                            {"name": "Cherry", "ml": ""},
                        ]
                    ),
                ),
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
            espresso = next(
                row for row in menu_rows if row["name"] == "Espresso Martini"
            )
            whiskey = next(row for row in menu_rows if row["name"] == "Whiskey Sour")
            fanta = next(row for row in menu_rows if row["name"] == "Fanta")
            self.assertTrue(espresso["image_filename"].startswith("images/"))
            self.assertIn(espresso["image_filename"], archive_names)
            self.assertEqual(whiskey["available"], "no")
            self.assertEqual(whiskey["sort_order"], "1")
            self.assertEqual(whiskey["image_focus_x"], "30.0")
            self.assertEqual(whiskey["image_focus_y"], "82.0")
            self.assertEqual(
                json.loads(whiskey["recipe"]),
                [
                    {"name": "Whiskey", "ml": "60"},
                    {"name": "Lemon juice", "ml": "30"},
                    {"name": "Cherry", "ml": ""},
                ],
            )
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
                SELECT description, category, image, available, sort_order, recipe,
                       image_focus_x, image_focus_y
                FROM menu_items WHERE name = 'Whiskey Sour'
                """
            ).fetchone()
            self.assertEqual(whiskey["description"], "Rollback recipe")
            self.assertEqual(whiskey["category"], "Cocktails")
            self.assertEqual(whiskey["available"], 0)
            self.assertEqual(whiskey["sort_order"], 1)
            self.assertEqual(whiskey["image_focus_x"], 30)
            self.assertEqual(whiskey["image_focus_y"], 82)
            self.assertEqual(
                json.loads(whiskey["recipe"]),
                [
                    {"name": "Whiskey", "ml": "60"},
                    {"name": "Lemon juice", "ml": "30"},
                    {"name": "Cherry", "ml": ""},
                ],
            )
            self.assertTrue(whiskey["image"].startswith("/uploads/"))
            restored_image = Path(self.app.config["UPLOAD_DIR"]) / Path(
                whiskey["image"]
            ).name
            self.assertEqual(restored_image.suffix, ".webp")
            with Image.open(restored_image) as restored:
                self.assertEqual(restored.format, "WEBP")
                self.assertEqual(restored.size, (640, 480))
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
