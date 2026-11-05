"""Persistent nonce replay protection and security audit storage."""

import json
import logging
from threading import RLock

import pymysql

from api_service4.app.utils.singleton import Singleton
from api_service4.config.init import get_config


class SecurityControlSystem(Singleton):
    _db_lock = RLock()
    _config = get_config()

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.logger = logging.getLogger("Security Control System")
        self.db_config = self._config.MYSQL_CONFIG
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
        self._create_tables()
        self._initialized = True

    def _create_tables(self):
        nonce_sql = """
        CREATE TABLE IF NOT EXISTS secure_request_nonces (
            nonce VARCHAR(96) PRIMARY KEY,
            request_id VARCHAR(96) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_secure_nonces_expires (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='应用层安全隧道防重放记录'
        """
        audit_sql = """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NULL,
            username VARCHAR(64) NULL,
            role VARCHAR(16) NULL,
            event_type VARCHAR(96) NOT NULL,
            resource_type VARCHAR(64) NULL,
            resource_id VARCHAR(128) NULL,
            operation VARCHAR(32) NOT NULL,
            result VARCHAR(16) NOT NULL,
            http_status INT NOT NULL,
            ip_address VARCHAR(64) NULL,
            request_method VARCHAR(12) NULL,
            request_path VARCHAR(255) NULL,
            details_json TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_audit_user_time (user_id, created_at),
            INDEX idx_audit_event_time (event_type, created_at),
            INDEX idx_audit_result_time (result, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安全审计日志'
        """
        with self._db_lock:
            self.cursor.execute(nonce_sql)
            self.cursor.execute(audit_sql)
            self.conn.commit()

    def consume_nonce(self, nonce, request_id, expires_at):
        """Atomically stores a nonce. False means the request is a replay."""
        try:
            with self._db_lock:
                self.cursor.execute("DELETE FROM secure_request_nonces WHERE expires_at <= CURRENT_TIMESTAMP")
                self.cursor.execute(
                    "INSERT INTO secure_request_nonces (nonce, request_id, expires_at) VALUES (%s, %s, %s)",
                    (nonce, request_id, expires_at),
                )
                self.conn.commit()
            return True
        except pymysql.IntegrityError:
            self.conn.rollback()
            return False
        except Exception:
            self.conn.rollback()
            raise

    def record_audit(
        self,
        *,
        event_type,
        operation,
        result,
        http_status,
        user=None,
        resource_type=None,
        resource_id=None,
        ip_address=None,
        request_method=None,
        request_path=None,
        details=None,
    ):
        user = user or {}
        safe_details = details if isinstance(details, dict) else {}
        try:
            with self._db_lock:
                self.cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        user_id, username, role, event_type, resource_type, resource_id,
                        operation, result, http_status, ip_address, request_method,
                        request_path, details_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user.get("user_id") or user.get("id"),
                        user.get("username"),
                        user.get("role"),
                        event_type,
                        resource_type,
                        str(resource_id) if resource_id is not None else None,
                        operation,
                        result,
                        int(http_status),
                        ip_address,
                        request_method,
                        request_path,
                        json.dumps(safe_details, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            self.logger.error("写入审计日志失败: %s", exc)

    def list_audit_logs(self, *, limit=100, event_type=None, result=None, user_id=None):
        limit = max(1, min(int(limit), 500))
        query = """
        SELECT id, user_id, username, role, event_type, resource_type, resource_id,
               operation, result, http_status, ip_address, request_method,
               request_path, details_json, created_at
        FROM audit_logs WHERE 1=1
        """
        params = []
        if event_type:
            query += " AND event_type = %s"
            params.append(event_type)
        if result:
            query += " AND result = %s"
            params.append(result)
        if user_id:
            query += " AND user_id = %s"
            params.append(int(user_id))
        query += " ORDER BY id DESC LIMIT %s"
        params.append(limit)
        with self._db_lock:
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            self.conn.commit()
        for row in rows:
            details_raw = row.pop("details_json", None)
            try:
                row["details"] = json.loads(details_raw) if details_raw else {}
            except (TypeError, ValueError):
                row["details"] = {}
            if row.get("created_at"):
                row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return rows
