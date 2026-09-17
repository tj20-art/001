import os
import re
import logging
import json
from threading import Lock

import pymysql

from api_service4.config.init import get_config
from api_service4.app.utils.singleton import Singleton
from api_service4.app.services.gm_crypto import (
    CertificateAlgorithmMismatchError,
    CertificateExpiredError,
    CertificateFormatError,
    CertificateIssuerMismatchError,
    CertificateNotYetValidError,
    CertificatePublicKeyMismatchError,
    CertificateUsernameMismatchError,
    CertificateVerificationError,
    gen_salt_hex,
    sm3_password_hash,
    sm4_encrypt_phone,
    sm4_decrypt_phone,
    sm4_encrypt_text,
    sm4_decrypt_text,
    generate_user_keypair_pem,
    verify_certificate_with_root,
)


class UserAuthSystem(Singleton):
    _db_lock = Lock()
    _config = get_config()

    def __init__(self, db_path=None, jwt_secret=None):
        if getattr(self, "_initialized", False):
            if jwt_secret:
                self.jwt_secret = jwt_secret
            return
        self.logger = logging.getLogger("User Auth System")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.use_mysql = hasattr(self._config, "USE_MYSQL") and self._config.USE_MYSQL
        self.db_config = self._config.MYSQL_CONFIG if self.use_mysql else {"path": db_path or self._config.USER_DB_PATH}
        self.jwt_secret = jwt_secret
        self.conn = None
        self.cursor = None

        try:
            self._init_db_connection()
            self._create_tables()
            self._initialized = True
            self.logger.info(f"用户认证系统初始化成功（{'MySQL' if self.use_mysql else 'SQLite'}环境）")
        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            raise

    def _init_db_connection(self):
        with self._db_lock:
            if self.use_mysql:
                self.conn = pymysql.connect(
                    host=self.db_config["host"],
                    port=self.db_config["port"],
                    user=self.db_config["user"],
                    password=self.db_config["password"],
                    db=self.db_config["db"],
                    charset=self.db_config["charset"],
                    autocommit=False,
                )
            else:
                import sqlite3
                self.conn = sqlite3.connect(self.db_config["path"])
            self.cursor = self.conn.cursor(pymysql.cursors.DictCursor if self.use_mysql else None)

    def _create_tables(self):
        if self.use_mysql:
            create_sql = '''
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(20) UNIQUE NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                phone VARCHAR(512) NOT NULL,
                role VARCHAR(10) NOT NULL DEFAULT 'user',
                sm2_private_key TEXT NOT NULL,
                sm2_public_key TEXT NOT NULL,
                auth_version INT NOT NULL DEFAULT 0,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            '''
        else:
            create_sql = '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(20) UNIQUE NOT NULL,
                password_hash VARCHAR(64) NOT NULL,
                salt VARCHAR(64) NOT NULL,
                phone TEXT NOT NULL,
                role VARCHAR(10) NOT NULL DEFAULT 'user',
                sm2_private_key TEXT NOT NULL,
                sm2_public_key TEXT NOT NULL,
                auth_version INTEGER NOT NULL DEFAULT 0,
                is_active TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            '''

        with self._db_lock:
            self.cursor.execute(create_sql)

            if self.use_mysql:
                refresh_token_sql = '''
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_id INT NOT NULL,
                    encrypted_token TEXT NOT NULL,
                    expiry TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                '''
            else:
                refresh_token_sql = '''
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    encrypted_token TEXT NOT NULL,
                    expiry TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                '''

            self.cursor.execute(refresh_token_sql)
            self.conn.commit()

        self._ensure_legacy_columns()

    def _ensure_legacy_columns(self):
        if self.use_mysql:
            required_columns = {
                "salt": "ALTER TABLE users ADD COLUMN salt VARCHAR(64) NOT NULL DEFAULT ''",
                "sm2_private_key": "ALTER TABLE users ADD COLUMN sm2_private_key TEXT NOT NULL",
                "sm2_public_key": "ALTER TABLE users ADD COLUMN sm2_public_key TEXT NOT NULL",
                "totp_secret": "ALTER TABLE users ADD COLUMN totp_secret TEXT NULL",
                "totp_enabled": "ALTER TABLE users ADD COLUMN totp_enabled TINYINT(1) NOT NULL DEFAULT 0",
                "totp_last_counter": "ALTER TABLE users ADD COLUMN totp_last_counter BIGINT NULL",
                "recovery_codes_json": "ALTER TABLE users ADD COLUMN recovery_codes_json LONGTEXT NULL",
                "auth_version": "ALTER TABLE users ADD COLUMN auth_version INT NOT NULL DEFAULT 0",
            }
            with self._db_lock:
                for col, ddl in required_columns.items():
                    self.cursor.execute("SHOW COLUMNS FROM users LIKE %s", (col,))
                    row = self.cursor.fetchone()
                    if not row:
                        self.cursor.execute(ddl)
                self.conn.commit()
        else:
            with self._db_lock:
                self.cursor.execute("PRAGMA table_info(users)")
                cols = {row[1] for row in self.cursor.fetchall()}
                alter_sqls = []
                if "salt" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN salt VARCHAR(64) NOT NULL DEFAULT ''")
                if "sm2_private_key" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN sm2_private_key TEXT NOT NULL DEFAULT ''")
                if "sm2_public_key" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN sm2_public_key TEXT NOT NULL DEFAULT ''")
                if "totp_secret" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN totp_secret TEXT NULL")
                if "totp_enabled" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN totp_enabled TINYINT(1) NOT NULL DEFAULT 0")
                if "totp_last_counter" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN totp_last_counter BIGINT NULL")
                if "recovery_codes_json" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN recovery_codes_json TEXT NULL")
                if "auth_version" not in cols:
                    alter_sqls.append("ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")
                for sql in alter_sqls:
                    self.cursor.execute(sql)
                self.conn.commit()

    def _validate_input(self, field_type, value):
        if field_type == "username":
            return bool(re.match(r"^[a-zA-Z0-9_]{5,20}$", value))
        if field_type == "password":
            return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()+=-]).{8,20}$", value))
        if field_type == "phone":
            return bool(re.match(r"^1[3-9]\d{9}$", value))
        return False

    def _get_root_cert_pem(self):
        package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        root_cert_path = os.path.abspath(
            os.getenv("ROOT_CERT_PATH", os.path.join(package_root, "certificates", "root_certificate.pem"))
        )
        if not os.path.exists(root_cert_path):
            raise FileNotFoundError(f"根证书文件未找到: {root_cert_path}")
        with open(root_cert_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    def _row_to_user_dict(self, row, include_private_key=False):
        if not row:
            return None

        if not self.use_mysql:
            columns = [col[0] for col in self.cursor.description]
            row = dict(zip(columns, row))

        user = dict(row)
        try:
            user["phone"] = sm4_decrypt_phone(user["phone"])
        except Exception:
            user["phone"] = "***decrypt_failed***"

        if not include_private_key:
            user.pop("sm2_private_key", None)
        return user

    def register(self, username, password, phone, role="user"):
        valid_roles = ["user", "merchant", "admin", "auditor"]
        if role not in valid_roles:
            self.logger.error("无效角色: %s，合法角色为 %s", role, valid_roles)
            return False, f"无效角色，仅支持{valid_roles}"

        if not self._validate_input("username", username):
            return False, "用户名格式错误（5-20位字母、数字、下划线）"
        if not self._validate_input("password", password):
            return False, "密码格式错误（需包含大小写字母、数字、特殊符号，8-20位）"
        if not self._validate_input("phone", phone):
            return False, "手机号格式错误（需为11位手机号，如13800138000）"

        salt_hex = gen_salt_hex(16)
        hashed_password = sm3_password_hash(password, salt_hex)
        phone_enc = sm4_encrypt_phone(phone)
        user_private_key_pem, user_public_key_pem = generate_user_keypair_pem()

        try:
            with self._db_lock:
                self.cursor.execute(
                    '''
                    INSERT INTO users (username, password_hash, salt, phone, role, sm2_private_key, sm2_public_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''',
                    (
                        username,
                        hashed_password,
                        salt_hex,
                        phone_enc,
                        role,
                        user_private_key_pem,
                        user_public_key_pem,
                    ),
                )
                self.conn.commit()
            return True, "注册成功"
        except pymysql.IntegrityError as e:
            if "Duplicate entry" in str(e):
                return False, f"用户名 {username} 已存在"
            return False, f"数据库约束错误: {str(e)}"
        except Exception as e:
            self.conn.rollback()
            return False, f"注册失败: {str(e)}"

    def authenticate_by_certificate(self, username, cert_data):
        """
        返回: (user_info, auth_error)
        auth_error 形如:
        {
            "status": 401,
            "message": "证书已过期",
            "reason": "expired"
        }
        """
        user_info = self.get_user(username, include_private_key=False)
        if not user_info:
            return None, {
                "status": 401,
                "message": "证书与用户不匹配",
                "reason": "user_not_found_or_mismatch",
            }

        try:
            root_cert_pem = self._get_root_cert_pem()
            verify_certificate_with_root(
                cert_pem_or_bytes=cert_data,
                root_cert_pem=root_cert_pem,
                expected_public_key_pem=user_info["sm2_public_key"],
                expected_username=username,
            )
            return {
                "id": user_info["id"],
                "username": user_info["username"],
                "role": user_info["role"],
                "sm2_public_key": user_info["sm2_public_key"],
                "totp_enabled": bool(user_info.get("totp_enabled")),
                "auth_version": int(user_info.get("auth_version") or 0),
            }, None
        except CertificateExpiredError:
            return None, {"status": 401, "message": "证书已过期", "reason": "expired"}
        except CertificateNotYetValidError:
            return None, {"status": 401, "message": "证书尚未生效", "reason": "not_yet_valid"}
        except CertificatePublicKeyMismatchError:
            return None, {"status": 401, "message": "证书与用户不匹配", "reason": "public_key_mismatch"}
        except CertificateUsernameMismatchError:
            return None, {"status": 401, "message": "证书与用户不匹配", "reason": "username_mismatch"}
        except CertificateIssuerMismatchError:
            return None, {"status": 401, "message": "证书不是由受信任 CA 签发", "reason": "issuer_mismatch"}
        except CertificateAlgorithmMismatchError:
            return None, {"status": 401, "message": "证书算法不符合国密要求", "reason": "algorithm_mismatch"}
        except CertificateFormatError as exc:
            return None, {"status": 400, "message": f"证书解析失败: {str(exc)}", "reason": "bad_certificate"}
        except CertificateVerificationError as exc:
            return None, {"status": 401, "message": str(exc) or "证书验证失败", "reason": "verification_failed"}
        except Exception as exc:
            self.logger.error("证书验证失败: %s", str(exc))
            return None, {"status": 500, "message": "证书验证过程中发生内部错误", "reason": "internal_error"}

    def authenticate(self, username, password):
        try:
            with self._db_lock:
                self.cursor.execute(
                    '''
                    SELECT id, username, password_hash, salt, role, sm2_public_key, auth_version
                    FROM users
                    WHERE username = %s AND is_active = 1
                    ''',
                    (username,),
                )
                user = self.cursor.fetchone()
                self.conn.commit()

            if not user:
                return False

            if self.use_mysql:
                user_id = user["id"]
                username = user["username"]
                hashed_password = user["password_hash"]
                salt_hex = user["salt"]
                role = user["role"]
                user_public_key = user["sm2_public_key"]
                auth_version = int(user.get("auth_version") or 0)
            else:
                user_id, username, hashed_password, salt_hex, role, user_public_key, auth_version = user

            calc = sm3_password_hash(password, salt_hex)
            if calc == hashed_password:
                return {
                    "id": user_id,
                    "username": username,
                    "role": role,
                    "sm2_public_key": user_public_key,
                    "auth_version": auth_version,
                }
            return False
        except Exception:
            return False

    def search_users(self, name=None, user_id=None, phone=None):
        query = "SELECT id, username, phone, role, is_active, created_at, totp_enabled FROM users WHERE 1=1"
        params = []

        if name:
            query += " AND username LIKE %s"
            params.append(f"%{name}%")
        if user_id:
            query += " AND id = %s"
            params.append(user_id)

        try:
            with self._db_lock:
                self.cursor.execute(query, params)
                if self.use_mysql:
                    users = self.cursor.fetchall()
                else:
                    columns = [col[0] for col in self.cursor.description]
                    users = [dict(zip(columns, row)) for row in self.cursor.fetchall()]
                self.conn.commit()

            normalized_users = []
            for item in users:
                normalized_users.append(self._row_to_user_dict(item, include_private_key=False))

            if phone:
                normalized_users = [u for u in normalized_users if phone in (u.get("phone") or "")]
            return normalized_users
        except Exception as e:
            self.logger.error(f"搜索用户失败: {str(e)}")
            return []

    def get_user(self, username, include_private_key=False):
        try:
            with self._db_lock:
                fields = "id, username, phone, role, is_active, created_at, sm2_public_key, totp_enabled, auth_version"
                if include_private_key:
                    fields += ", sm2_private_key"
                self.cursor.execute(
                    f'''
                    SELECT {fields}
                    FROM users
                    WHERE username = %s AND is_active = 1
                    ''',
                    (username,),
                )
                user = self.cursor.fetchone()
                self.conn.commit()
            return self._row_to_user_dict(user, include_private_key=include_private_key)
        except Exception as e:
            self.logger.error(f"查询用户 {username} 失败: {str(e)}")
            return None

    def get_user_by_id(self, user_id, include_private_key=False):
        try:
            with self._db_lock:
                fields = "id, username, phone, role, is_active, created_at, sm2_public_key, totp_enabled, auth_version"
                if include_private_key:
                    fields += ", sm2_private_key"
                self.cursor.execute(
                    f'''
                    SELECT {fields}
                    FROM users
                    WHERE id = %s AND is_active = 1
                    ''',
                    (user_id,),
                )
                user = self.cursor.fetchone()
                self.conn.commit()
            return self._row_to_user_dict(user, include_private_key=include_private_key)
        except Exception as e:
            self.logger.error(f"按ID查询用户 {user_id} 失败: {str(e)}")
            return None

    def store_refresh_token_hash(self, user_id, token_hash, expiry):
        """保存刷新令牌哈希；沿用旧列名以兼容现有数据库结构。"""
        try:
            with self._db_lock:
                self.cursor.execute(
                    '''
                    INSERT INTO refresh_tokens (user_id, encrypted_token, expiry)
                    VALUES (%s, %s, %s)
                    ''',
                    (user_id, token_hash, expiry),
                )
                self.conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"存储刷新令牌哈希失败: {str(e)}")
            self.conn.rollback()
            return False

    def consume_refresh_token_hash(self, user_id, token_hash):
        """原子删除并消费一个未过期的刷新令牌哈希。"""
        try:
            with self._db_lock:
                expiry_expr = "NOW()" if self.use_mysql else "CURRENT_TIMESTAMP"
                self.cursor.execute(
                    f'''
                    DELETE FROM refresh_tokens
                    WHERE user_id = %s
                      AND encrypted_token = %s
                      AND expiry > {expiry_expr}
                    ''',
                    (user_id, token_hash),
                )
                consumed = self.cursor.rowcount == 1
                self.conn.commit()
                return consumed
        except Exception as e:
            self.logger.error(f"消费刷新令牌失败: {str(e)}")
            self.conn.rollback()
            return False

    def delete_user_by_username(self, username):
        try:
            with self._db_lock:
                self.cursor.execute(
                    """
                    DELETE FROM users
                    WHERE username = %s
                    """,
                    (username,),
                )
                self.conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"按用户名删除用户 {username} 失败: {str(e)}")
            self.conn.rollback()
            return False

    def set_user_role(self, user_id, role):
        valid_roles = {"user", "merchant", "admin", "auditor"}
        if role not in valid_roles:
            return False, "无效角色"
        try:
            with self._db_lock:
                self.cursor.execute("SELECT role FROM users WHERE id = %s AND is_active = 1", (user_id,))
                current = self.cursor.fetchone()
                if not current:
                    self.conn.rollback()
                    return False, "用户不存在"
                current_role = current["role"] if self.use_mysql else current[0]
                reset_mfa = role not in {"admin", "auditor"}
                if reset_mfa:
                    self.cursor.execute(
                        """
                        UPDATE users SET role = %s, totp_secret = NULL, totp_enabled = 0,
                                         totp_last_counter = NULL, recovery_codes_json = NULL,
                                         auth_version = auth_version + 1
                        WHERE id = %s
                        """,
                        (role, user_id),
                    )
                else:
                    self.cursor.execute(
                        "UPDATE users SET role = %s, auth_version = auth_version + 1 WHERE id = %s",
                        (role, user_id),
                    )
                self.cursor.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
                self.conn.commit()
            return True, f"角色已从 {current_role} 更新为 {role}"
        except Exception as exc:
            self.conn.rollback()
            return False, f"角色更新失败: {str(exc)}"

    def admin_reset_user_info(self, user_id, username=None, phone=None, new_password=None):
        """管理员重置账号资料，并撤销该账号已签发的全部登录令牌。"""
        updates = []
        params = []

        if username is not None:
            username = str(username).strip()
            if not self._validate_input("username", username):
                return False, "用户名格式错误（5-20位字母、数字、下划线）", None
            updates.append("username = %s")
            params.append(username)

        if phone is not None:
            phone = str(phone).strip()
            if not self._validate_input("phone", phone):
                return False, "手机号格式错误（需为11位手机号）", None
            updates.append("phone = %s")
            params.append(sm4_encrypt_phone(phone))

        if new_password not in (None, ""):
            new_password = str(new_password)
            if not self._validate_input("password", new_password):
                return False, "密码格式错误（需包含大小写字母、数字、特殊符号，8-20位）", None
            salt_hex = gen_salt_hex(16)
            updates.extend(["password_hash = %s", "salt = %s"])
            params.extend([sm3_password_hash(new_password, salt_hex), salt_hex])

        if not updates:
            return False, "请至少提供一项需要重置的信息", None

        updates.append("auth_version = auth_version + 1")
        params.append(user_id)
        try:
            with self._db_lock:
                if self.use_mysql:
                    self.conn.begin()
                else:
                    self.cursor.execute("BEGIN")
                self.cursor.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = %s AND is_active = 1",
                    params,
                )
                if self.cursor.rowcount != 1:
                    self.conn.rollback()
                    return False, "用户不存在", None
                self.cursor.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
                self.conn.commit()
            return True, "用户信息已重置，原登录状态已失效", {
                "username": username,
                "phone": phone,
                "password_reset": new_password not in (None, ""),
            }
        except pymysql.IntegrityError as exc:
            self.conn.rollback()
            if "Duplicate entry" in str(exc) or "UNIQUE constraint failed" in str(exc):
                return False, "该用户名已被使用", None
            return False, f"数据库约束错误: {str(exc)}", None
        except Exception as exc:
            self.conn.rollback()
            return False, f"重置用户信息失败: {str(exc)}", None

    def reset_user_mfa(self, user_id):
        """清除 TOTP 密钥、计数器和恢复码，特权账号下次登录时必须重新绑定。"""
        try:
            with self._db_lock:
                if self.use_mysql:
                    self.conn.begin()
                else:
                    self.cursor.execute("BEGIN")
                self.cursor.execute(
                    """
                    UPDATE users
                    SET totp_secret = NULL, totp_enabled = 0, totp_last_counter = NULL,
                        recovery_codes_json = NULL, auth_version = auth_version + 1
                    WHERE id = %s AND is_active = 1
                    """,
                    (user_id,),
                )
                if self.cursor.rowcount != 1:
                    self.conn.rollback()
                    return False, "用户不存在"
                self.cursor.execute("DELETE FROM refresh_tokens WHERE user_id = %s", (user_id,))
                self.conn.commit()
            return True, "双因素认证已重置，原密钥、恢复码和登录状态均已失效"
        except Exception as exc:
            self.conn.rollback()
            return False, f"重置双因素认证失败: {str(exc)}"

    def get_mfa_record(self, user_id):
        try:
            with self._db_lock:
                self.cursor.execute(
                    """
                    SELECT id, username, role, totp_secret, totp_enabled,
                           totp_last_counter, recovery_codes_json
                    FROM users WHERE id = %s AND is_active = 1
                    """,
                    (user_id,),
                )
                row = self.cursor.fetchone()
                self.conn.commit()
            if not row:
                return None
            if not self.use_mysql:
                columns = [column[0] for column in self.cursor.description]
                row = dict(zip(columns, row))
            record = dict(row)
            if record.get("totp_secret"):
                record["totp_secret"] = sm4_decrypt_text(record["totp_secret"])
            try:
                record["recovery_codes"] = json.loads(record.get("recovery_codes_json") or "[]")
            except (TypeError, ValueError):
                record["recovery_codes"] = []
            return record
        except Exception as exc:
            self.logger.error("读取 MFA 配置失败: %s", exc)
            return None

    def enable_totp(self, user_id, secret, recovery_code_hashes, counter):
        try:
            encrypted_secret = sm4_encrypt_text(secret)
            with self._db_lock:
                self.cursor.execute(
                    """
                    UPDATE users
                    SET totp_secret = %s, totp_enabled = 1, totp_last_counter = %s,
                        recovery_codes_json = %s
                    WHERE id = %s AND role IN ('admin', 'auditor') AND is_active = 1
                    """,
                    (
                        encrypted_secret,
                        int(counter),
                        json.dumps(recovery_code_hashes, separators=(",", ":")),
                        user_id,
                    ),
                )
                updated = self.cursor.rowcount == 1
                self.conn.commit()
            return updated
        except Exception:
            self.conn.rollback()
            return False

    def consume_totp_counter(self, user_id, counter):
        """Atomic monotonic update prevents the same TOTP timestep from being reused."""
        try:
            with self._db_lock:
                self.cursor.execute(
                    """
                    UPDATE users SET totp_last_counter = %s
                    WHERE id = %s AND totp_enabled = 1
                      AND (totp_last_counter IS NULL OR totp_last_counter < %s)
                    """,
                    (int(counter), user_id, int(counter)),
                )
                consumed = self.cursor.rowcount == 1
                self.conn.commit()
            return consumed
        except Exception:
            self.conn.rollback()
            return False

    def consume_recovery_code(self, user_id, code_hash):
        try:
            with self._db_lock:
                self.conn.begin()
                self.cursor.execute(
                    "SELECT recovery_codes_json FROM users WHERE id = %s AND is_active = 1 FOR UPDATE",
                    (user_id,),
                )
                row = self.cursor.fetchone()
                if not row:
                    self.conn.rollback()
                    return False
                raw_codes = row["recovery_codes_json"] if self.use_mysql else row[0]
                try:
                    codes = json.loads(raw_codes or "[]")
                except (TypeError, ValueError):
                    codes = []
                if code_hash not in codes:
                    self.conn.rollback()
                    return False
                remaining = [item for item in codes if item != code_hash]
                self.cursor.execute(
                    "UPDATE users SET recovery_codes_json = %s WHERE id = %s",
                    (json.dumps(remaining, separators=(",", ":")), user_id),
                )
                self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            self.logger.info("数据库连接已关闭")

    def __del__(self):
        self.close()

    def update_user_info(self, user_id, old_password, new_username=None, new_password=None, phone=None):
        try:
            with self._db_lock:
                self.cursor.execute(
                    '''
                    SELECT id, password_hash, salt, phone
                    FROM users
                    WHERE id = %s AND is_active = 1
                    ''',
                    (user_id,),
                )
                user = self.cursor.fetchone()

                if not user:
                    return False, "用户不存在或已禁用"

                if self.use_mysql:
                    hashed_password = user["password_hash"]
                    salt_hex = user["salt"]
                    db_phone_enc = user["phone"]
                else:
                    _, hashed_password, salt_hex, db_phone_enc = user

                calc_old = sm3_password_hash(old_password, salt_hex)
                if calc_old != hashed_password:
                    return False, "旧密码验证失败"

                try:
                    db_phone_plain = sm4_decrypt_phone(db_phone_enc)
                except Exception:
                    return False, "手机号解密失败（请检查SM4_KEY_HEX配置或历史数据格式）"

                if phone != db_phone_plain:
                    return False, "手机号验证失败"

                update_fields = []
                params = []

                if new_username and self._validate_input("username", new_username):
                    update_fields.append("username = %s")
                    params.append(new_username)

                if new_password and self._validate_input("password", new_password):
                    new_salt_hex = gen_salt_hex(16)
                    new_hashed = sm3_password_hash(new_password, new_salt_hex)
                    update_fields.append("password_hash = %s")
                    params.append(new_hashed)
                    update_fields.append("salt = %s")
                    params.append(new_salt_hex)

                if not update_fields:
                    return False, "没有需要更新的有效信息"

                params.append(user_id)
                query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
                self.cursor.execute(query, params)
                self.conn.commit()
                return True, "信息更新成功"
        except pymysql.IntegrityError as e:
            self.conn.rollback()
            if "Duplicate entry" in str(e):
                return False, f"用户名 {new_username} 已存在"
            return False, f"数据库错误: {str(e)}"
        except Exception as e:
            self.conn.rollback()
            return False, f"更新失败: {str(e)}"
