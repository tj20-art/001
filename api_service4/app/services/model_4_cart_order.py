import logging
import random
from datetime import datetime
from threading import RLock

import pymysql

from api_service4.app.utils.singleton import Singleton
from api_service4.config.init import get_config


class CartOrderSystem(Singleton):
    _db_lock = RLock()
    _config = get_config()

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.logger = logging.getLogger("Cart Order System")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.db_config = self._config.MYSQL_CONFIG
        self.conn = None
        self.cursor = None
        try:
            self._init_db_connection()
            self._create_tables()
            self._initialized = True
            self.logger.info("购物车/订单系统初始化成功（MySQL环境）")
        except Exception as exc:
            self.logger.error(f"购物车/订单系统初始化失败: {str(exc)}")
            raise

    def _init_db_connection(self):
        with self._db_lock:
            self.conn = pymysql.connect(
                host=self.db_config["host"],
                port=self.db_config["port"],
                user=self.db_config["user"],
                password=self.db_config["password"],
                db=self.db_config["db"],
                charset=self.db_config["charset"],
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
            )
            self.cursor = self.conn.cursor()

    def _begin_tx(self):
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
        self.conn.begin()

    def _create_tables(self):
        cart_sql = """
        CREATE TABLE IF NOT EXISTS cart_items (
            id INT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            selected TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_cart_user_product (user_id, product_id),
            INDEX idx_cart_user_id (user_id),
            INDEX idx_cart_product_id (product_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='购物车表';
        """
        order_sql = """
        CREATE TABLE IF NOT EXISTS orders (
            id INT PRIMARY KEY AUTO_INCREMENT,
            order_no VARCHAR(64) NOT NULL,
            user_id INT NOT NULL,
            total_amount_cents INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pay_time TIMESTAMP NULL DEFAULT NULL,
            cancel_time TIMESTAMP NULL DEFAULT NULL,
            UNIQUE KEY uk_orders_order_no (order_no),
            INDEX idx_orders_user_id (user_id),
            INDEX idx_orders_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单主表';
        """
        order_item_sql = """
        CREATE TABLE IF NOT EXISTS order_items (
            id INT PRIMARY KEY AUTO_INCREMENT,
            order_id INT NOT NULL,
            product_id INT NOT NULL,
            seller_id INT NOT NULL,
            product_name VARCHAR(100) NOT NULL,
            price_cents INT NOT NULL,
            quantity INT NOT NULL,
            INDEX idx_order_items_order_id (order_id),
            INDEX idx_order_items_product_id (product_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';
        """
        with self._db_lock:
            self._begin_tx()
            self.cursor.execute(cart_sql)
            self.cursor.execute(order_sql)
            self.cursor.execute(order_item_sql)
            self.conn.commit()
            self._ensure_payment_schema()

    def _ensure_payment_schema(self):
        required_columns = {
            "bank_trade_no": "ALTER TABLE orders ADD COLUMN bank_trade_no VARCHAR(64) NULL",
            "paid_amount_cents": "ALTER TABLE orders ADD COLUMN paid_amount_cents INT NULL",
            "payment_notify_time": "ALTER TABLE orders ADD COLUMN payment_notify_time TIMESTAMP NULL DEFAULT NULL",
        }
        with self._db_lock:
            self._begin_tx()
            for column, ddl in required_columns.items():
                self.cursor.execute("SHOW COLUMNS FROM orders LIKE %s", (column,))
                if not self.cursor.fetchone():
                    self.cursor.execute(ddl)
            self.cursor.execute("SHOW INDEX FROM orders WHERE Key_name = 'idx_orders_bank_trade_no'")
            if not self.cursor.fetchone():
                self.cursor.execute("CREATE INDEX idx_orders_bank_trade_no ON orders (bank_trade_no)")
            self.conn.commit()

    @staticmethod
    def _normalize_cart_item(row):
        item = dict(row)

        # 兼容旧字段：id 仍然保留为购物车条目 ID
        # 新字段：cart_item_id 明确表示购物车条目 ID
        if item.get("cart_item_id") is None and item.get("id") is not None:
            item["cart_item_id"] = item["id"]
        if item.get("id") is None and item.get("cart_item_id") is not None:
            item["id"] = item["cart_item_id"]

        item["quantity"] = int(item.get("quantity") or 0)
        item["selected"] = bool(item.get("selected"))
        item["price_cents"] = int(item.get("price_cents") or 0)
        item["price"] = item["price_cents"] / 100.0
        item["stock"] = int(item.get("stock") or 0)
        item["subtotal_cents"] = item["price_cents"] * item["quantity"]
        item["subtotal"] = item["subtotal_cents"] / 100.0
        return item

    @staticmethod
    def _normalize_order_row(row):
        item = dict(row)
        item["total_amount_cents"] = int(item.get("total_amount_cents") or 0)
        item["total_amount"] = item["total_amount_cents"] / 100.0
        if "paid_amount_cents" in item:
            item["paid_amount_cents"] = int(item.get("paid_amount_cents") or 0)
            item["paid_amount"] = item["paid_amount_cents"] / 100.0 if item["paid_amount_cents"] else None
        return item

    @staticmethod
    def _normalize_order_item(row):
        item = dict(row)
        item["price_cents"] = int(item.get("price_cents") or 0)
        item["price"] = item["price_cents"] / 100.0
        item["quantity"] = int(item.get("quantity") or 0)
        item["subtotal_cents"] = item["price_cents"] * item["quantity"]
        item["subtotal"] = item["subtotal_cents"] / 100.0
        return item

    @staticmethod
    def _generate_order_no():
        return datetime.utcnow().strftime("%Y%m%d%H%M%S%f") + f"{random.randint(1000, 9999)}"

    def add_to_cart(self, user_id, product_id, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return False, "数量格式错误，需为整数"
        if quantity <= 0:
            return False, "数量必须大于0"

        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    "SELECT id, stock, status FROM products WHERE id = %s AND status = 'on_sale'",
                    (product_id,),
                )
                product = self.cursor.fetchone()
                if not product:
                    self.conn.rollback()
                    return False, "商品不存在或已下架"
                if int(product["stock"]) < quantity:
                    self.conn.rollback()
                    return False, "库存不足"

                self.cursor.execute(
                    "SELECT id, quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
                    (user_id, product_id),
                )
                existing = self.cursor.fetchone()
                if existing:
                    new_quantity = int(existing["quantity"]) + quantity
                    if new_quantity > int(product["stock"]):
                        self.conn.rollback()
                        return False, "购物车数量超过库存"
                    self.cursor.execute(
                        "UPDATE cart_items SET quantity = %s, selected = 1 WHERE id = %s AND user_id = %s",
                        (new_quantity, existing["id"], user_id),
                    )
                else:
                    self.cursor.execute(
                        "INSERT INTO cart_items (user_id, product_id, quantity, selected) VALUES (%s, %s, %s, 1)",
                        (user_id, product_id, quantity),
                    )
                self.conn.commit()
            return True, "已加入购物车"
        except Exception as exc:
            self.conn.rollback()
            return False, f"加入购物车失败: {str(exc)}"

    def list_cart_items(self, user_id):
        query = """
        SELECT
            c.id AS cart_item_id,
            c.id,
            c.user_id,
            c.product_id,
            c.quantity,
            c.selected,
            p.name AS product_name,
            p.category,
            p.description,
            p.price_cents,
            p.stock,
            p.status,
            p.image_url,
            p.image_urls,
            p.video_url,
            p.seller_id,
            c.created_at,
            c.updated_at
        FROM cart_items c
        JOIN products p ON p.id = c.product_id
        WHERE c.user_id = %s
        ORDER BY c.id DESC
        """
        with self._db_lock:
            self.cursor.execute(query, (user_id,))
            rows = self.cursor.fetchall()
            self.conn.commit()
        return [self._normalize_cart_item(row) for row in rows]

    def update_cart_item(self, cart_item_id, user_id, quantity=None, selected=None):
        update_fields = []
        params = []
        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    """
                    SELECT c.id, c.product_id, p.stock, p.status
                    FROM cart_items c
                    JOIN products p ON p.id = c.product_id
                    WHERE c.id = %s AND c.user_id = %s
                    """,
                    (cart_item_id, user_id),
                )
                cart_item = self.cursor.fetchone()
                if not cart_item:
                    self.conn.rollback()
                    return False, "购物车条目不存在或无权限修改"

                if quantity is not None:
                    quantity = int(quantity)
                    if quantity <= 0:
                        self.conn.rollback()
                        return False, "数量必须大于0"
                    if cart_item["status"] != "on_sale":
                        self.conn.rollback()
                        return False, "商品已下架，不能修改数量"
                    if quantity > int(cart_item["stock"]):
                        self.conn.rollback()
                        return False, "库存不足"
                    update_fields.append("quantity = %s")
                    params.append(quantity)

                if selected is not None:
                    update_fields.append("selected = %s")
                    params.append(1 if bool(selected) else 0)

                if not update_fields:
                    self.conn.rollback()
                    return False, "没有需要更新的字段"

                params.extend([cart_item_id, user_id])
                self.cursor.execute(
                    f"UPDATE cart_items SET {', '.join(update_fields)} WHERE id = %s AND user_id = %s",
                    params,
                )
                self.conn.commit()
            return True, "购物车更新成功"
        except Exception as exc:
            self.conn.rollback()
            return False, f"更新购物车失败: {str(exc)}"

    def remove_cart_item(self, cart_item_id, user_id):
        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s", (cart_item_id, user_id))
                if self.cursor.rowcount == 0:
                    self.conn.rollback()
                    return False, "购物车条目不存在或无权限删除"
                self.conn.commit()
            return True, "购物车条目删除成功"
        except Exception as exc:
            self.conn.rollback()
            return False, f"删除购物车条目失败: {str(exc)}"

    def clear_cart(self, user_id):
        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
                self.conn.commit()
            return True, "购物车已清空"
        except Exception as exc:
            self.conn.rollback()
            return False, f"清空购物车失败: {str(exc)}"

    def set_selected_bulk(self, user_id, selected, cart_item_ids=None):
        try:
            with self._db_lock:
                self._begin_tx()
                if cart_item_ids:
                    placeholders = ",".join(["%s"] * len(cart_item_ids))
                    query = f"UPDATE cart_items SET selected = %s WHERE user_id = %s AND id IN ({placeholders})"
                    params = [1 if bool(selected) else 0, user_id, *cart_item_ids]
                else:
                    query = "UPDATE cart_items SET selected = %s WHERE user_id = %s"
                    params = [1 if bool(selected) else 0, user_id]
                self.cursor.execute(query, params)
                self.conn.commit()
            return True, "购物车勾选状态更新成功"
        except Exception as exc:
            self.conn.rollback()
            return False, f"更新勾选状态失败: {str(exc)}"

    def create_order_from_selected_cart(self, user_id):
        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    """
                    SELECT
                        c.id AS cart_id,
                        c.product_id,
                        c.quantity,
                        p.seller_id,
                        p.name AS product_name,
                        p.price_cents,
                        p.stock,
                        p.status
                    FROM cart_items c
                    JOIN products p ON p.id = c.product_id
                    WHERE c.user_id = %s AND c.selected = 1
                    FOR UPDATE
                    """,
                    (user_id,),
                )
                cart_rows = self.cursor.fetchall()
                if not cart_rows:
                    self.conn.rollback()
                    return False, "没有已勾选的购物车商品"

                total_amount_cents = 0
                for row in cart_rows:
                    if row["status"] != "on_sale":
                        self.conn.rollback()
                        return False, f"商品 {row['product_name']} 已下架，无法下单"
                    if int(row["stock"]) < int(row["quantity"]):
                        self.conn.rollback()
                        return False, f"商品 {row['product_name']} 库存不足"
                    total_amount_cents += int(row["price_cents"]) * int(row["quantity"])

                order_no = self._generate_order_no()
                self.cursor.execute(
                    "INSERT INTO orders (order_no, user_id, total_amount_cents, status) VALUES (%s, %s, %s, 'pending')",
                    (order_no, user_id, total_amount_cents),
                )
                order_id = self.cursor.lastrowid

                for row in cart_rows:
                    self.cursor.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, seller_id, product_name, price_cents, quantity)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            row["product_id"],
                            row["seller_id"],
                            row["product_name"],
                            row["price_cents"],
                            row["quantity"],
                        ),
                    )
                    self.cursor.execute(
                        "UPDATE products SET stock = stock - %s WHERE id = %s AND status = 'on_sale' AND stock >= %s",
                        (row["quantity"], row["product_id"], row["quantity"]),
                    )
                    if self.cursor.rowcount == 0:
                        self.conn.rollback()
                        return False, f"商品 {row['product_name']} 扣减库存失败"

                cart_ids = [row["cart_id"] for row in cart_rows]
                placeholders = ",".join(["%s"] * len(cart_ids))
                self.cursor.execute(
                    f"DELETE FROM cart_items WHERE user_id = %s AND id IN ({placeholders})",
                    [user_id, *cart_ids],
                )
                self.conn.commit()
            return True, {"order_id": order_id, "order_no": order_no, "message": "订单创建成功"}
        except Exception as exc:
            self.conn.rollback()
            return False, f"创建订单失败: {str(exc)}"

    def list_orders(self, user_id, status=None):
        query = "SELECT id, order_no, user_id, total_amount_cents, status, created_at, pay_time, cancel_time, bank_trade_no, paid_amount_cents, payment_notify_time FROM orders WHERE user_id = %s"
        params = [user_id]
        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY id DESC"
        with self._db_lock:
            self.cursor.execute(query, params)
            orders = self.cursor.fetchall()
            self.conn.commit()
        return [self._normalize_order_row(row) for row in orders]

    def get_order_detail(self, order_id, user_id):
        with self._db_lock:
            self.cursor.execute(
                "SELECT id, order_no, user_id, total_amount_cents, status, created_at, pay_time, cancel_time, bank_trade_no, paid_amount_cents, payment_notify_time FROM orders WHERE id = %s AND user_id = %s",
                (order_id, user_id),
            )
            order = self.cursor.fetchone()
            if not order:
                self.conn.commit()
                return None
            self.cursor.execute(
                "SELECT id, order_id, product_id, seller_id, product_name, price_cents, quantity FROM order_items WHERE order_id = %s ORDER BY id ASC",
                (order_id,),
            )
            items = self.cursor.fetchall()
            self.conn.commit()
        order_data = self._normalize_order_row(order)
        order_data["items"] = [self._normalize_order_item(item) for item in items]
        return order_data

    def get_order_by_no(self, order_no):
        with self._db_lock:
            self.cursor.execute(
                "SELECT id, order_no, user_id, total_amount_cents, status, created_at, pay_time, cancel_time, bank_trade_no, paid_amount_cents, payment_notify_time FROM orders WHERE order_no = %s",
                (order_no,),
            )
            order = self.cursor.fetchone()
            self.conn.commit()
        return self._normalize_order_row(order) if order else None

    def mark_order_paid_by_no(self, order_no, amount_cents, bank_trade_no):
        try:
            amount_cents = int(amount_cents)
        except (TypeError, ValueError):
            return False, "支付金额格式错误"

        if not order_no or not bank_trade_no:
            return False, "缺少订单号或银行流水号"

        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    "SELECT id, order_no, total_amount_cents, status FROM orders WHERE order_no = %s FOR UPDATE",
                    (order_no,),
                )
                order = self.cursor.fetchone()
                if not order:
                    self.conn.rollback()
                    return False, "订单不存在"

                if int(order["total_amount_cents"]) != amount_cents:
                    self.conn.rollback()
                    return False, "支付金额与订单金额不一致"

                if order["status"] == "paid":
                    self.conn.commit()
                    return True, "订单已支付，重复回调已幂等忽略"

                if order["status"] != "pending":
                    self.conn.rollback()
                    return False, f"当前订单状态不允许支付：{order['status']}"

                self.cursor.execute(
                    """
                    UPDATE orders
                    SET status = 'paid',
                        pay_time = CURRENT_TIMESTAMP,
                        bank_trade_no = %s,
                        paid_amount_cents = %s,
                        payment_notify_time = CURRENT_TIMESTAMP
                    WHERE order_no = %s AND status = 'pending'
                    """,
                    (bank_trade_no, amount_cents, order_no),
                )
                if self.cursor.rowcount == 0:
                    self.conn.rollback()
                    return False, "订单状态更新失败"
                self.conn.commit()
            return True, "订单支付成功"
        except Exception as exc:
            self.conn.rollback()
            return False, f"更新订单支付状态失败: {str(exc)}"

    def cancel_order(self, order_id, user_id):
        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    "SELECT id, status FROM orders WHERE id = %s AND user_id = %s FOR UPDATE",
                    (order_id, user_id),
                )
                order = self.cursor.fetchone()
                if not order:
                    self.conn.rollback()
                    return False, "订单不存在或无权限取消"
                if order["status"] != "pending":
                    self.conn.rollback()
                    return False, "只有待支付订单可以取消"

                self.cursor.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = %s FOR UPDATE",
                    (order_id,),
                )
                items = self.cursor.fetchall()
                for item in items:
                    self.cursor.execute(
                        "UPDATE products SET stock = stock + %s WHERE id = %s",
                        (item["quantity"], item["product_id"]),
                    )
                self.cursor.execute(
                    "UPDATE orders SET status = 'cancelled', cancel_time = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
                    (order_id, user_id),
                )
                self.conn.commit()
            return True, "订单已取消"
        except Exception as exc:
            self.conn.rollback()
            return False, f"取消订单失败: {str(exc)}"

    def close(self):
        if self.conn:
            self.conn.close()
            self.logger.info("购物车/订单数据库连接已关闭")

    def __del__(self):
        self.close()
