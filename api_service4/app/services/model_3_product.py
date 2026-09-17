import decimal
import json
import logging
from threading import Lock

import pymysql

from api_service4.app.utils.singleton import Singleton
from api_service4.config.init import get_config


class ProductSystem(Singleton):
    _db_lock = Lock()
    _config = get_config()

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.logger = logging.getLogger("Product System")
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
            self._create_table()
            self._ensure_schema()
            self._initialized = True
            self.logger.info("商品系统初始化成功（MySQL环境）")
        except Exception as exc:
            self.logger.error(f"商品系统初始化失败: {str(exc)}")
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
        """
        当前工程使用长连接 + Singleton + autocommit=False。
        如果不在每次写操作前重置事务，之前查询留下的事务快照会导致后续读到旧库存。
        """
        try:
            self.conn.commit()
        except Exception:
            self.conn.rollback()
        self.conn.begin()

    def _create_table(self):
        create_sql = """
        CREATE TABLE IF NOT EXISTS products (
            id INT PRIMARY KEY AUTO_INCREMENT,
            seller_id INT NOT NULL,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NULL,
            description TEXT NULL,
            price_cents INT NOT NULL,
            stock INT NOT NULL,
            image_url TEXT NULL,
            image_urls LONGTEXT NULL,
            video_url TEXT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'on_sale',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_products_seller_id (seller_id),
            INDEX idx_products_status (status),
            INDEX idx_products_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';
        """
        with self._db_lock:
            self._begin_tx()
            self.cursor.execute(create_sql)
            self.conn.commit()

    def _ensure_schema(self):
        required_columns = {
            "seller_id": "ALTER TABLE products ADD COLUMN seller_id INT NOT NULL DEFAULT 0",
            "category": "ALTER TABLE products ADD COLUMN category VARCHAR(50) NULL",
            "price_cents": "ALTER TABLE products ADD COLUMN price_cents INT NOT NULL DEFAULT 0",
            "stock": "ALTER TABLE products ADD COLUMN stock INT NOT NULL DEFAULT 0",
            "image_url": "ALTER TABLE products ADD COLUMN image_url TEXT NULL",
            "image_urls": "ALTER TABLE products ADD COLUMN image_urls LONGTEXT NULL",
            "video_url": "ALTER TABLE products ADD COLUMN video_url TEXT NULL",
            "status": "ALTER TABLE products ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'on_sale'",
            "description": "ALTER TABLE products ADD COLUMN description TEXT NULL",
            "created_at": "ALTER TABLE products ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "ALTER TABLE products ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
        }
        with self._db_lock:
            self._begin_tx()
            for column, ddl in required_columns.items():
                self.cursor.execute("SHOW COLUMNS FROM products LIKE %s", (column,))
                if not self.cursor.fetchone():
                    self.cursor.execute(ddl)

            self.cursor.execute("SHOW INDEX FROM products WHERE Key_name = 'idx_products_seller_id'")
            if not self.cursor.fetchone():
                self.cursor.execute("CREATE INDEX idx_products_seller_id ON products (seller_id)")
            self.cursor.execute("SHOW INDEX FROM products WHERE Key_name = 'idx_products_status'")
            if not self.cursor.fetchone():
                self.cursor.execute("CREATE INDEX idx_products_status ON products (status)")
            self.cursor.execute("SHOW INDEX FROM products WHERE Key_name = 'idx_products_name'")
            if not self.cursor.fetchone():
                self.cursor.execute("CREATE INDEX idx_products_name ON products (name)")

            self.cursor.execute("SHOW INDEX FROM products WHERE Column_name = 'name' AND Non_unique = 0")
            unique_name_indexes = self.cursor.fetchall()
            for index in unique_name_indexes:
                key_name = index.get("Key_name")
                if key_name and key_name not in {"PRIMARY"}:
                    self.cursor.execute(f"ALTER TABLE products DROP INDEX `{key_name}`")

            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'price'")
            if self.cursor.fetchone():
                self.cursor.execute(
                    "UPDATE products SET price_cents = ROUND(price * 100) WHERE price_cents = 0 AND price IS NOT NULL"
                )

            self.cursor.execute("SHOW COLUMNS FROM products LIKE 'quantity'")
            if self.cursor.fetchone():
                self.cursor.execute("UPDATE products SET stock = quantity WHERE stock = 0 AND quantity IS NOT NULL")

            self.conn.commit()

    @staticmethod
    def _serialize_image_urls(image_urls):
        if image_urls is None:
            return None
        if isinstance(image_urls, str):
            return image_urls
        return json.dumps(image_urls, ensure_ascii=False)

    @staticmethod
    def _normalize_status(status):
        allowed = {"on_sale", "off_shelf"}
        status = (status or "on_sale").strip().lower()
        if status not in allowed:
            raise ValueError("status 仅支持 on_sale/off_shelf")
        return status

    @staticmethod
    def _price_to_cents(price):
        try:
            normalized = decimal.Decimal(str(price)).quantize(decimal.Decimal("0.00"))
        except Exception as exc:
            raise ValueError("价格格式错误，需为数字") from exc
        if normalized <= 0:
            raise ValueError("价格必须大于0")
        return int(normalized * 100)

    @staticmethod
    def _clean_product_row(row):
        item = dict(row)
        item["price_cents"] = int(item.get("price_cents") or 0)
        item["price"] = item["price_cents"] / 100.0
        item["stock"] = int(item.get("stock") or 0)
        return item

    def create_product(
        self,
        seller_id,
        name,
        description,
        price,
        stock,
        category=None,
        image_url=None,
        image_urls=None,
        video_url=None,
    ):
        if not seller_id:
            return False, "缺少 seller_id"
        if not name or not str(name).strip():
            return False, "商品名称不能为空"
        if stock is None:
            return False, "库存不能为空"
        try:
            stock = int(stock)
        except (TypeError, ValueError):
            return False, "库存格式错误，需为整数"
        if stock < 0:
            return False, "库存不能为负数"

        try:
            price_cents = self._price_to_cents(price)
        except ValueError as exc:
            return False, str(exc)

        try:
            with self._db_lock:
                self._begin_tx()
                self.cursor.execute(
                    """
                    INSERT INTO products (
                        seller_id, name, category, description, price_cents, stock,
                        image_url, image_urls, video_url, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'on_sale')
                    """,
                    (
                        seller_id,
                        str(name).strip(),
                        (category or "").strip() or None,
                        (description or "").strip(),
                        price_cents,
                        stock,
                        image_url,
                        self._serialize_image_urls(image_urls),
                        video_url,
                    ),
                )
                product_id = self.cursor.lastrowid
                self.conn.commit()
            return True, {"product_id": product_id, "message": "商品发布成功"}
        except Exception as exc:
            self.conn.rollback()
            return False, f"商品发布失败: {str(exc)}"

    def list_products(self, product_id=None, name=None, seller_id=None, status=None, include_off_shelf=False):
        query = (
            "SELECT id, seller_id, name, category, description, price_cents, stock, image_url, image_urls, video_url, status, "
            "created_at, updated_at FROM products WHERE 1=1"
        )
        params = []
        if product_id:
            query += " AND id = %s"
            params.append(product_id)
        if name:
            query += " AND name LIKE %s"
            params.append(f"%{name}%")
        if seller_id:
            query += " AND seller_id = %s"
            params.append(seller_id)
        if status:
            query += " AND status = %s"
            params.append(self._normalize_status(status))
        elif not include_off_shelf:
            query += " AND status = 'on_sale'"

        query += " ORDER BY id DESC"
        with self._db_lock:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            # 关键修复：读完立即提交，结束只读事务，避免后续一直读取旧库存快照
            self.conn.commit()
        return [self._clean_product_row(row) for row in rows]

    def get_product_by_id(self, product_id, current_user_id=None, include_off_shelf=False):
        query = (
            "SELECT id, seller_id, name, category, description, price_cents, stock, image_url, image_urls, video_url, status, "
            "created_at, updated_at FROM products WHERE id = %s"
        )
        params = [product_id]
        if not include_off_shelf:
            query += " AND (status = 'on_sale'"
            if current_user_id:
                query += " OR seller_id = %s"
                params.append(current_user_id)
            query += ")"
        query += " LIMIT 1"

        with self._db_lock:
            self.cursor.execute(query, params)
            row = self.cursor.fetchone()
            # 关键修复：读完立即提交，结束只读事务，避免后续一直读取旧库存快照
            self.conn.commit()
        return self._clean_product_row(row) if row else None

    def update_product_for_seller(self, product_id, seller_id, **kwargs):
        if not kwargs:
            return False, "没有需要更新的字段"

        allowed_fields = {
            "name": "name",
            "category": "category",
            "description": "description",
            "price": "price_cents",
            "stock": "stock",
            "image_url": "image_url",
            "image_urls": "image_urls",
            "video_url": "video_url",
            "status": "status",
        }
        update_fields = []
        params = []

        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue
            column = allowed_fields[key]
            if key == "price":
                try:
                    value = self._price_to_cents(value)
                except ValueError as exc:
                    return False, str(exc)
            elif key == "stock":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return False, "库存格式错误，需为整数"
                if value < 0:
                    return False, "库存不能为负数"
            elif key == "image_urls":
                value = self._serialize_image_urls(value)
            elif key == "status":
                try:
                    value = self._normalize_status(value)
                except ValueError as exc:
                    return False, str(exc)
            elif key in {"name", "category", "description"}:
                value = (value or "").strip()
                if key == "name" and not value:
                    return False, "商品名称不能为空"
                if key == "category" and not value:
                    value = None
            update_fields.append(f"{column} = %s")
            params.append(value)

        if not update_fields:
            return False, "没有有效的更新字段"

        try:
            with self._db_lock:
                self._begin_tx()

                # 1. 先确认商品存在，并且属于当前卖家
                self.cursor.execute(
                    "SELECT id FROM products WHERE id = %s AND seller_id = %s FOR UPDATE",
                    (product_id, seller_id),
                )
                product = self.cursor.fetchone()

                if not product:
                    self.conn.rollback()
                    return False, "商品不存在或无权限修改"

                # 2. 再执行更新
                # 不要用 rowcount == 0 判断权限，因为字段值没变化时 rowcount 也可能是 0
                params.extend([product_id, seller_id])
                query = f"""
                    UPDATE products
                    SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND seller_id = %s
                """
                self.cursor.execute(query, params)

                self.conn.commit()

            return True, "商品更新成功"

        except Exception as exc:
            self.conn.rollback()
            return False, f"更新商品失败: {str(exc)}"

    def off_shelf_product(self, product_id, seller_id):
        return self.update_product_for_seller(product_id, seller_id, status="off_shelf")

    def close(self):
        if self.conn:
            self.conn.close()
            self.logger.info("商品数据库连接已关闭")

    def __del__(self):
        self.close()
