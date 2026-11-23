import logging
import sqlite3
from contextlib import contextmanager

import pytest

from api_service4.app.services.model_3_product import ProductSystem
from api_service4.app.services.model_4_cart_order import CartOrderSystem
from api_service4.app.utils.pagination import parse_pagination


class TestCursor:
    __test__ = False

    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, query, params=()):
        query = query.replace("%s", "?").replace(" FOR UPDATE", "")
        query = query.replace("ON DUPLICATE KEY UPDATE order_id = order_id", "ON CONFLICT DO NOTHING")
        self.cursor.execute(query, params)

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class TestReadPool:
    __test__ = False

    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def cursor(self, *, consistent=False):
        yield TestCursor(self.connection)

    def close(self):
        pass


class TestConnection(sqlite3.Connection):
    __test__ = False

    def begin(self):
        self.execute("BEGIN")


@pytest.fixture
def commerce():
    db = sqlite3.connect(":memory:", factory=TestConnection)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, seller_id INTEGER, name TEXT, category TEXT, description TEXT,
            price_cents INTEGER, stock INTEGER, status TEXT, image_url TEXT, image_urls TEXT, video_url TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT, is_active INTEGER);
        CREATE TABLE cart_items (
            id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER,
            selected INTEGER, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, order_no TEXT UNIQUE, user_id INTEGER, total_amount_cents INTEGER,
            status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, pay_time TEXT, cancel_time TEXT,
            bank_trade_no TEXT, paid_amount_cents INTEGER, payment_notify_time TEXT
        );
        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, seller_id INTEGER,
            product_name TEXT, price_cents INTEGER, quantity INTEGER
        );
        CREATE TABLE order_checkout_requests (
            user_id INTEGER, request_key TEXT, order_id INTEGER, PRIMARY KEY (user_id, request_key)
        );
        INSERT INTO products (id, seller_id, name, category, price_cents, stock, status) VALUES
            (1, 10, 'Ceramic mug', 'Home', 2200, 5, 'on_sale'),
            (2, 10, 'Glass tumbler', 'Home', 1600, 1, 'off_shelf'),
            (3, 15, 'Travel charger', 'Tech', 3600, 9, 'on_sale');
        INSERT INTO users VALUES (7, 'customer', 'user', 1), (8, 'former_buyer', 'merchant', 0), (9, 'empty', 'user', 1);
        INSERT INTO cart_items (id, user_id, product_id, quantity, selected) VALUES (1, 7, 1, 2, 1), (2, 8, 3, 1, 1);
    """)
    orders = object.__new__(CartOrderSystem)
    orders.conn, orders.cursor = db, TestCursor(db)
    orders.logger = logging.getLogger(__name__)
    orders._read_pool = TestReadPool(db)
    products = object.__new__(ProductSystem)
    products.conn = None
    products._read_pool = orders._read_pool
    try:
        yield db, orders, products
    finally:
        orders.conn = None
        db.close()


def test_checkout_retry_reuses_order_without_touching_a_new_cart_selection(commerce):
    db, orders, _ = commerce
    key = "b81f2e55-6004-4c7c-9803-27976cc8278c"
    ok, first = orders.create_order_from_selected_cart(7, key)
    assert ok and not first["replayed"]
    assert first["order"]["items"][0]["quantity"] == 2
    db.execute("INSERT INTO cart_items (id, user_id, product_id, quantity, selected) VALUES (3, 7, 1, 1, 1)")
    db.commit()

    ok, retry = orders.create_order_from_selected_cart(7, key)
    assert ok and retry["replayed"] and retry["order"]["id"] == first["order"]["id"]
    assert db.execute("SELECT stock FROM products WHERE id = 1").fetchone()[0] == 3
    assert db.execute("SELECT COUNT(*) FROM cart_items WHERE user_id = 7").fetchone()[0] == 1

    ok, other = orders.create_order_from_selected_cart(8, key)
    assert ok and other["order"]["id"] != first["order"]["id"]
    assert orders.get_order_status(first["order"]["order_no"], 8) is None
    assert orders.get_order_status(first["order"]["order_no"], 7)["status"] == "pending"
    orders.mark_order_paid_by_no(first["order"]["order_no"], 4400, "test-bank-reference")
    assert orders.get_order_status(first["order"]["order_no"], 7)["status"] == "paid"


def test_failed_checkout_can_retry_same_key_after_stock_check(commerce):
    db, orders, _ = commerce
    key = "d6d88eac-f5e2-4fa2-87f1-77dc07fa37e4"
    db.execute("UPDATE cart_items SET quantity = 10 WHERE user_id = 7")
    db.commit()
    assert not orders.create_order_from_selected_cart(7, key)[0]
    assert db.execute("SELECT COUNT(*) FROM order_checkout_requests").fetchone()[0] == 0
    db.execute("UPDATE cart_items SET quantity = 1 WHERE user_id = 7")
    db.commit()
    assert orders.create_order_from_selected_cart(7, key)[0]


def test_pages_use_filtered_counts_and_scope_totals(commerce):
    _, orders, products = commerce
    items, total, overview = products.list_products(page=2, page_size=1, compact=True, include_overview=True)
    assert [row["id"] for row in items] == [1]
    assert total == 2 and overview["categories"] == ["Home", "Tech"]
    assert "description" not in items[0]

    items, total, overview = products.list_products(
        seller_id=10, status="off_shelf", include_off_shelf=True, include_overview=True
    )
    assert [row["id"] for row in items] == [2]
    assert total == 1 and overview["summary"] == {"total": 2, "on_sale": 1, "off_shelf": 1, "stock": 6}
    assert products.list_products(status="off_shelf")[1] == 0

    assert orders.create_order_from_selected_cart(7)[0]
    items, total, summary = orders.list_orders(7, "paid", page=1, page_size=1)
    assert items == [] and total == 0 and summary == {"total": 1, "pending": 1}
    assert parse_pagination({}) == (1, 24)
    with pytest.raises(ValueError):
        parse_pagination({"page_size": "101"})


def test_cart_management_includes_empty_and_disabled_accounts(commerce):
    db, orders, _ = commerce
    owners, total = orders.list_cart_owners(page=1, page_size=2)
    assert total == 3
    assert [(row["user_id"], row["quantity_total"]) for row in owners] == [(9, 0), (8, 1)]
    owners, total = orders.list_cart_owners(username="former_")
    assert total == 1 and owners[0]["role"] == "merchant" and not owners[0]["is_active"]
    assert orders.get_cart_for_admin(9)[1] == []
    assert orders.get_cart_for_admin(99) is None

    db.execute("DELETE FROM products WHERE id = 3")
    db.commit()
    owner, items = orders.get_cart_for_admin(8)
    assert owner["username"] == "former_buyer"
    assert items[0]["product_id"] == 3 and items[0]["product_name"] is None
    assert orders.list_cart_items(8) == []
    assert orders.remove_cart_item(2, 8)[0]


def test_cart_quantity_and_deletion_are_scoped_to_the_target_user(commerce):
    db, orders, _ = commerce
    assert not orders.update_cart_item(1, 8, quantity=3)[0]
    assert not orders.remove_cart_item(2, 7)[0]
    assert not orders.update_cart_item(1, 7, quantity=6)[0]
    assert orders.update_cart_item(1, 7, quantity=4)[0]
    _, items = orders.get_cart_for_admin(7)
    assert items[0]["quantity"] == 4 and items[0]["selected"]
    assert orders.clear_cart(7, require_owner=True)[0]
    assert orders.get_cart_for_admin(7)[1] == []
    assert orders.get_cart_for_admin(8)[1][0]["id"] == 2
    assert db.execute("SELECT stock FROM products WHERE id = 1").fetchone()[0] == 5
    assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    assert not orders.clear_cart(99, require_owner=True)[0]
