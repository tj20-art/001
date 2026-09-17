import rsa
import os
import logging
from datetime import datetime

# LEGACY: RSA token encryption used temporarily.
# TODO (Week 3-4): migrate refresh token protection to SM2 / certificate-based flow.


class RSAService:
    def __init__(self, key_size=2048, key_dir=None):
        self.key_size = key_size
        package_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.key_dir = os.path.abspath(key_dir or os.path.join(package_root, "key_zheng"))
        self.public_key = None
        self.private_key = None
        self.logger = logging.getLogger("RSA Service")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    def generate_keys(self):  # 移除encrypt_password参数
        self.logger.info("开始生成RSA密钥对")
        public_key, private_key = rsa.newkeys(self.key_size)
        self.public_key = public_key
        self.private_key = private_key
        os.makedirs(self.key_dir, exist_ok=True)
        # 存储公钥（明文）
        with open(f"{self.key_dir}/public.pem", "wb") as f:
            f.write(public_key.save_pkcs1())
        # 存储私钥（明文，测试阶段临时处理）
        with open(f"{self.key_dir}/private.pem", "wb") as f:
            f.write(private_key.save_pkcs1())
        self.logger.info("密钥对生成并保存成功")

    def load_keys(self):  # 移除encrypt_password参数
        self.logger.info("开始从文件加载密钥")
        try:
            # 加载公钥
            with open(f"{self.key_dir}/public.pem", "rb") as f:
                self.public_key = rsa.PublicKey.load_pkcs1(f.read())
            # 加载私钥（明文，测试阶段）
            with open(f"{self.key_dir}/private.pem", "rb") as f:
                self.private_key = rsa.PrivateKey.load_pkcs1(f.read())
            self.logger.info("密钥从文件加载完成")
            return True
        except FileNotFoundError:
            self.logger.warning("未找到密钥文件，将生成新的密钥对")
            self.generate_keys()  # 调用无参方法
            return True
        except Exception as e:
            self.logger.error(f"加载密钥失败: {str(e)}")
            return False

    def encrypt(self, plaintext):
        if not self.public_key:
            self.logger.error("公钥未加载，无法加密")
            return None
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        elif not isinstance(plaintext, bytes):
            self.logger.error("明文需为字符串或字节")
            return None
        try:
            ciphertext = rsa.encrypt(plaintext, self.public_key)
            return ciphertext.hex()  # 返回十六进制字符串，便于存储
        except Exception as e:
            self.logger.error(f"加密失败: {str(e)}")
            return None

    def decrypt(self, ciphertext_hex):
        if not self.private_key:
            self.logger.error("私钥未加载，无法解密")
            return None
        try:
            ciphertext = bytes.fromhex(ciphertext_hex)
            plaintext = rsa.decrypt(ciphertext, self.private_key)
            return plaintext.decode("utf-8")
        except Exception as e:
            self.logger.error(f"解密失败: {str(e)}")
            return None
