import os
import re
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Optional, Tuple

from gmssl import sm3, func
from gmssl.sm4 import CryptSM4, SM4_ENCRYPT, SM4_DECRYPT

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec


class CertificateVerificationError(Exception):
    """证书验证失败基类。"""


class CertificateFormatError(CertificateVerificationError):
    """证书格式非法或不可解析。"""


class CertificateExpiredError(CertificateVerificationError):
    """证书已过期。"""


class CertificateNotYetValidError(CertificateVerificationError):
    """证书尚未到生效时间。"""


class CertificateIssuerMismatchError(CertificateVerificationError):
    """证书签发者与受信任 Root CA 不匹配。"""


class CertificatePublicKeyMismatchError(CertificateVerificationError):
    """证书公钥与数据库中的用户公钥不匹配。"""


class CertificateUsernameMismatchError(CertificateVerificationError):
    """证书主题用户名与请求用户不匹配。"""


class CertificateAlgorithmMismatchError(CertificateVerificationError):
    """证书算法不符合国密要求。"""


def _normalize_pem_text(pem_text: str) -> str:
    return "\n".join(line.rstrip() for line in pem_text.strip().splitlines()) + "\n"


@lru_cache(maxsize=1)
def _openssl_bin() -> Optional[str]:
    return shutil.which("openssl")


@lru_cache(maxsize=1)
def openssl_supports_sm2() -> bool:
    openssl = _openssl_bin()
    if not openssl:
        return False

    try:
        result = subprocess.run(
            [openssl, "ecparam", "-list_curves"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False

    return "SM2" in result.stdout.upper()


def _run_openssl(args, input_bytes: Optional[bytes] = None) -> bytes:
    openssl = _openssl_bin()
    if not openssl:
        raise RuntimeError("系统未安装 openssl，无法执行国密证书操作")

    try:
        completed = subprocess.run(
            [openssl, *args],
            input=input_bytes,
            check=True,
            capture_output=True,
            timeout=20,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
        stdout = exc.stdout.decode("utf-8", errors="ignore") if exc.stdout else ""
        raise RuntimeError((stderr or stdout or "openssl 执行失败").strip()) from exc

    return completed.stdout


def _safe_not_before(cert: x509.Certificate) -> datetime:
    value = getattr(cert, "not_valid_before_utc", None)
    if value is not None:
        return value
    return cert.not_valid_before.replace(tzinfo=timezone.utc)


def _safe_not_after(cert: x509.Certificate) -> datetime:
    value = getattr(cert, "not_valid_after_utc", None)
    if value is not None:
        return value
    return cert.not_valid_after.replace(tzinfo=timezone.utc)


def _load_certificate_any_format(cert_pem_or_bytes) -> Tuple[x509.Certificate, bytes]:
    if isinstance(cert_pem_or_bytes, str):
        raw = cert_pem_or_bytes.encode("utf-8")
    else:
        raw = cert_pem_or_bytes

    if not raw:
        raise CertificateFormatError("证书内容为空")

    try:
        cert = x509.load_pem_x509_certificate(raw)
        pem = cert.public_bytes(serialization.Encoding.PEM)
        return cert, pem
    except Exception:
        pass

    try:
        cert = x509.load_der_x509_certificate(raw)
        pem = cert.public_bytes(serialization.Encoding.PEM)
        return cert, pem
    except Exception as exc:
        raise CertificateFormatError(f"证书解析失败: {str(exc)}") from exc


def _extract_cn_from_subject_line(subject_line: str) -> Optional[str]:
    patterns = [
        r"CN\s*=\s*([^,\/\n]+)",
        r"/CN=([^/\n]+)",
        r"commonName\s*=\s*([^,\/\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, subject_line, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_certificate_common_name(cert_pem_or_bytes) -> str:
    cert, pem = _load_certificate_any_format(cert_pem_or_bytes)

    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if attrs and attrs[0].value.strip():
            return attrs[0].value.strip()
    except Exception:
        pass

    openssl = _openssl_bin()
    if openssl:
        try:
            subject_line = _run_openssl(["x509", "-noout", "-subject"], input_bytes=pem).decode("utf-8", errors="ignore")
            cn = _extract_cn_from_subject_line(subject_line)
            if cn:
                return cn
        except Exception:
            pass

    raise CertificateFormatError("证书中缺少可用的 CN 字段")


def _check_certificate_validity(cert: x509.Certificate):
    now = datetime.now(timezone.utc)
    not_before = _safe_not_before(cert)
    not_after = _safe_not_after(cert)

    if now < not_before:
        raise CertificateNotYetValidError("证书尚未生效")
    if now > not_after:
        raise CertificateExpiredError("证书已过期")


def _verify_certificate_with_cryptography(
    cert_pem_or_bytes,
    root_cert_pem,
    expected_public_key_pem=None,
    expected_username=None,
    enforce_gm: bool = False,
):
    cert, cert_pem = _load_certificate_any_format(cert_pem_or_bytes)
    root_cert, _ = _load_certificate_any_format(root_cert_pem)

    if cert.issuer != root_cert.subject:
        raise CertificateIssuerMismatchError("证书签发者与 Root CA 不匹配")

    _check_certificate_validity(cert)

    if enforce_gm:
        sig_name = getattr(cert.signature_algorithm_oid, "_name", "") or str(cert.signature_algorithm_oid)
        curve_name = getattr(getattr(cert.public_key(), "curve", None), "name", "")
        joined = f"{sig_name} {curve_name}".lower()
        if "sm2" not in joined and "sm3" not in joined:
            raise CertificateAlgorithmMismatchError("当前证书不是 SM2/SM3 体系")

    try:
        root_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            ec.ECDSA(cert.signature_hash_algorithm),
        )
    except Exception as exc:
        raise CertificateVerificationError("证书签名校验失败") from exc

    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        cert_cn = attrs[0].value.strip() if attrs else None
    except Exception as exc:
        raise CertificateFormatError("证书中缺少 CN 字段") from exc

    if expected_username and cert_cn != expected_username:
        raise CertificateUsernameMismatchError("证书用户名与系统用户不匹配")

    if expected_public_key_pem:
        try:
            cert_pub_pem = cert.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
        except Exception as exc:
            raise CertificateFormatError("无法导出证书公钥") from exc

        if _normalize_pem_text(cert_pub_pem) != _normalize_pem_text(expected_public_key_pem):
            raise CertificatePublicKeyMismatchError("证书公钥与数据库中的用户公钥不匹配")

    return cert, cert_pem


def _verify_certificate_with_openssl(
    cert_pem_or_bytes,
    root_cert_pem,
    expected_public_key_pem=None,
    expected_username=None,
    enforce_gm: bool = False,
):
    cert, cert_pem = _load_certificate_any_format(cert_pem_or_bytes)
    _, root_cert_pem_bytes = _load_certificate_any_format(root_cert_pem)
    _check_certificate_validity(cert)

    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "user.crt")
        root_path = os.path.join(tmpdir, "root.crt")
        with open(cert_path, "wb") as f:
            f.write(cert_pem)
        with open(root_path, "wb") as f:
            f.write(root_cert_pem_bytes)

        try:
            verify_stdout = _run_openssl(["verify", "-CAfile", root_path, cert_path]).decode("utf-8", errors="ignore")
        except RuntimeError as exc:
            raise CertificateVerificationError(f"证书签名校验失败: {str(exc)}") from exc

        if "OK" not in verify_stdout:
            raise CertificateVerificationError("证书签名校验失败")

        subject_line = _run_openssl(["x509", "-noout", "-subject", "-in", cert_path]).decode("utf-8", errors="ignore")
        issuer_line = _run_openssl(["x509", "-noout", "-issuer", "-in", cert_path]).decode("utf-8", errors="ignore")
        root_subject_line = _run_openssl(["x509", "-noout", "-subject", "-in", root_path]).decode("utf-8", errors="ignore")
        dates_text = _run_openssl(["x509", "-noout", "-dates", "-in", cert_path]).decode("utf-8", errors="ignore")
        cert_pubkey = _run_openssl(["x509", "-pubkey", "-noout", "-in", cert_path]).decode("utf-8", errors="ignore")
        cert_text = _run_openssl(["x509", "-text", "-noout", "-in", cert_path]).decode("utf-8", errors="ignore")

    if issuer_line.split("=", 1)[-1].strip() != root_subject_line.split("=", 1)[-1].strip():
        raise CertificateIssuerMismatchError("证书签发者与 Root CA 不匹配")

    if expected_username:
        cert_cn = _extract_cn_from_subject_line(subject_line)
        if not cert_cn:
            raise CertificateFormatError("证书中缺少 CN 字段")
        if cert_cn != expected_username:
            raise CertificateUsernameMismatchError("证书用户名与系统用户不匹配")

    if expected_public_key_pem:
        if _normalize_pem_text(cert_pubkey) != _normalize_pem_text(expected_public_key_pem):
            raise CertificatePublicKeyMismatchError("证书公钥与数据库中的用户公钥不匹配")

    if enforce_gm:
        upper_text = cert_text.upper()
        if "SM2" not in upper_text or "SM3" not in upper_text:
            raise CertificateAlgorithmMismatchError("当前证书不是 SM2/SM3 体系")

    not_before = None
    not_after = None
    for line in dates_text.splitlines():
        if line.startswith("notBefore="):
            not_before = parsedate_to_datetime(line.split("=", 1)[1].strip())
        elif line.startswith("notAfter="):
            not_after = parsedate_to_datetime(line.split("=", 1)[1].strip())

    if not_before and not_after:
        now = datetime.now(timezone.utc)
        not_before = not_before.astimezone(timezone.utc)
        not_after = not_after.astimezone(timezone.utc)
        if now < not_before:
            raise CertificateNotYetValidError("证书尚未生效")
        if now > not_after:
            raise CertificateExpiredError("证书已过期")

    return cert, cert_pem


def generate_root_ca_real(common_name="MyRootCA"):
    """
    生成根 CA 证书。
    优先使用 openssl 的 SM2/SM3 方案；如果当前环境不支持 SM2，则回退到 ECDSA 兼容方案。
    返回：private_key_pem, public_key_pem, root_cert_pem
    """
    if openssl_supports_sm2():
        with tempfile.TemporaryDirectory() as tmpdir:
            ca_key = os.path.join(tmpdir, "ca.key")
            ca_pub = os.path.join(tmpdir, "ca_pub.pem")
            ca_csr = os.path.join(tmpdir, "ca.csr")
            ca_crt = os.path.join(tmpdir, "ca.crt")
            extfile = os.path.join(tmpdir, "ca_ext.cnf")

            with open(extfile, "w", encoding="utf-8") as f:
                f.write(
                    "[v3_ca]\n"
                    "basicConstraints=critical,CA:TRUE\n"
                    "keyUsage=critical,keyCertSign,cRLSign,digitalSignature\n"
                    "subjectKeyIdentifier=hash\n"
                    "authorityKeyIdentifier=keyid:always,issuer\n"
                )

            _run_openssl(["ecparam", "-genkey", "-name", "SM2", "-out", ca_key])
            _run_openssl(["ec", "-in", ca_key, "-pubout", "-out", ca_pub])
            _run_openssl([
                "req", "-new", "-sm3", "-key", ca_key,
                "-subj", f"/CN={common_name}",
                "-out", ca_csr,
            ])
            _run_openssl([
                "x509", "-req", "-sm3", "-days", "3650",
                "-signkey", ca_key,
                "-in", ca_csr,
                "-out", ca_crt,
                "-extfile", extfile,
                "-extensions", "v3_ca",
            ])

            with open(ca_key, "r", encoding="utf-8") as f:
                private_key_pem = f.read()
            with open(ca_pub, "r", encoding="utf-8") as f:
                public_key_pem = f.read()
            with open(ca_crt, "r", encoding="utf-8") as f:
                root_cert_pem = f.read()

            return private_key_pem, public_key_pem, root_cert_pem

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=private_key, algorithm=hashes.SHA256())
    )

    root_cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return private_key_pem, public_key_pem, root_cert_pem



def generate_user_keypair_pem():
    """
    生成用户密钥对。
    优先生成 SM2 密钥；若环境不支持则回退到 ECDSA 兼容方案。
    """
    if openssl_supports_sm2():
        with tempfile.TemporaryDirectory() as tmpdir:
            user_key = os.path.join(tmpdir, "user.key")
            user_pub = os.path.join(tmpdir, "user_pub.pem")
            _run_openssl(["ecparam", "-genkey", "-name", "SM2", "-out", user_key])
            _run_openssl(["ec", "-in", user_key, "-pubout", "-out", user_pub])
            with open(user_key, "r", encoding="utf-8") as f:
                private_key_pem = f.read()
            with open(user_pub, "r", encoding="utf-8") as f:
                public_key_pem = f.read()
            return private_key_pem, public_key_pem

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key_pem, public_key_pem


def sign_user_certificate(
    user_public_key_pem,
    root_private_key_pem,
    root_cert_pem,
    username,
    user_private_key_pem: Optional[str] = None,
):
    """
    使用 Root CA 根私钥签发用户 X.509 证书。

    说明：
    - 若服务器环境支持 openssl + SM2，且提供 user_private_key_pem，则优先签发真正的 SM2/SM3 用户证书。
    - 否则回退到 cryptography 的兼容模式证书签发。
    """
    openssl_error = None

    if openssl_supports_sm2() and user_private_key_pem:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                ca_key = os.path.join(tmpdir, "ca.key")
                ca_crt = os.path.join(tmpdir, "ca.crt")
                user_key = os.path.join(tmpdir, "user.key")
                user_pub = os.path.join(tmpdir, "user_pub.pem")
                user_csr = os.path.join(tmpdir, "user.csr")
                user_crt = os.path.join(tmpdir, "user.crt")
                serial = os.path.join(tmpdir, "ca.srl")
                extfile = os.path.join(tmpdir, "user_ext.cnf")

                with open(extfile, "w", encoding="utf-8") as f:
                    f.write(
                        "[v3_usr]\n"
                        "basicConstraints=critical,CA:FALSE\n"
                        "keyUsage=critical,digitalSignature,keyEncipherment\n"
                        "extendedKeyUsage=clientAuth\n"
                        "subjectKeyIdentifier=hash\n"
                        "authorityKeyIdentifier=keyid,issuer\n"
                    )

                with open(ca_key, "w", encoding="utf-8") as f:
                    f.write(root_private_key_pem)
                with open(ca_crt, "w", encoding="utf-8") as f:
                    f.write(root_cert_pem)
                with open(user_key, "w", encoding="utf-8") as f:
                    f.write(user_private_key_pem)

                _run_openssl(["ec", "-in", user_key, "-pubout", "-out", user_pub])
                with open(user_pub, "r", encoding="utf-8") as f:
                    derived_user_public_key_pem = f.read()

                if user_public_key_pem and _normalize_pem_text(user_public_key_pem) != _normalize_pem_text(derived_user_public_key_pem):
                    raise ValueError("用户私钥与数据库中的公钥不匹配，无法签发证书")

                _run_openssl([
                    "req", "-new", "-sm3", "-key", user_key,
                    "-subj", f"/CN={username}",
                    "-out", user_csr,
                ])
                _run_openssl([
                    "x509", "-req", "-sm3", "-days", "365",
                    "-CA", ca_crt,
                    "-CAkey", ca_key,
                    "-CAserial", serial,
                    "-CAcreateserial",
                    "-in", user_csr,
                    "-out", user_crt,
                    "-extfile", extfile,
                    "-extensions", "v3_usr",
                ])

                with open(user_crt, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as exc:
            openssl_error = exc

    try:
        public_key_obj = serialization.load_pem_public_key(user_public_key_pem.encode("utf-8"))
    except Exception as exc:
        raise ValueError(f"用户公钥 PEM 格式错误: {str(exc)}") from exc

    try:
        root_private_key = serialization.load_pem_private_key(
            root_private_key_pem.encode("utf-8"),
            password=None,
        )
    except Exception as exc:
        raise ValueError(f"根私钥 PEM 格式错误: {str(exc)}") from exc

    try:
        root_cert = x509.load_pem_x509_certificate(root_cert_pem.encode("utf-8"))
    except Exception as exc:
        raise ValueError(f"根证书 PEM 格式错误: {str(exc)}") from exc

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, username)])
    issuer = root_cert.subject
    user_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key_obj)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(private_key=root_private_key, algorithm=hashes.SHA256())
    )
    try:
        return user_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    except Exception as exc:
        if openssl_error:
            raise RuntimeError(f"OpenSSL SM2签发失败: {openssl_error}; fallback签发也失败: {exc}") from exc
        raise


def verify_certificate_with_root(
    cert_pem_or_bytes,
    root_cert_pem,
    expected_public_key_pem=None,
    expected_username=None,
    enforce_gm: Optional[bool] = None,
):
    """
    使用根证书校验用户证书签名，并额外完成：
    1. 有效期检查
    2. 签发者检查
    3. CN 检查
    4. 用户公钥绑定检查
    5. 国密算法检查（当环境具备 SM2 能力时默认开启）
    """
    if enforce_gm is None:
        enforce_gm = openssl_supports_sm2()

    if _openssl_bin():
        cert, _ = _verify_certificate_with_openssl(
            cert_pem_or_bytes=cert_pem_or_bytes,
            root_cert_pem=root_cert_pem,
            expected_public_key_pem=expected_public_key_pem,
            expected_username=expected_username,
            enforce_gm=enforce_gm,
        )
        return cert

    cert, _ = _verify_certificate_with_cryptography(
        cert_pem_or_bytes=cert_pem_or_bytes,
        root_cert_pem=root_cert_pem,
        expected_public_key_pem=expected_public_key_pem,
        expected_username=expected_username,
        enforce_gm=enforce_gm,
    )
    return cert


def sm3_hex(data: bytes) -> str:
    return sm3.sm3_hash(func.bytes_to_list(data))


def gen_salt_hex(nbytes: int = 16) -> str:
    return secrets.token_hex(nbytes)


def sm3_password_hash(password: str, salt_hex: str) -> str:
    salt_bytes = bytes.fromhex(salt_hex)
    data = password.encode("utf-8") + salt_bytes
    return sm3_hex(data)


def _get_sm4_key_bytes() -> bytes:
    key_hex = os.getenv("SM4_KEY_HEX", "")
    if key_hex:
        key = bytes.fromhex(key_hex)
        if len(key) != 16:
            raise ValueError("SM4_KEY_HEX must represent 16 bytes (32 hex chars).")
        return key

    fallback = "00112233445566778899aabbccddeeff"
    return bytes.fromhex(fallback)


def sm4_encrypt_text(plaintext: str) -> str:
    key = _get_sm4_key_bytes()
    iv = secrets.token_bytes(16)

    crypt = CryptSM4()
    crypt.set_key(key, SM4_ENCRYPT)

    data = str(plaintext).encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    data_padded = data + bytes([pad_len]) * pad_len

    cipher = crypt.crypt_cbc(iv, data_padded)
    return f"{iv.hex()}:{cipher.hex()}"


def sm4_decrypt_text(stored: str) -> str:
    key = _get_sm4_key_bytes()
    if ":" not in stored:
        raise ValueError("Invalid encrypted phone format")

    iv_hex, cipher_hex = stored.split(":", 1)
    iv = bytes.fromhex(iv_hex)
    cipher = bytes.fromhex(cipher_hex)

    crypt = CryptSM4()
    crypt.set_key(key, SM4_DECRYPT)
    data_padded = crypt.crypt_cbc(iv, cipher)

    pad_len = data_padded[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Invalid padding")
    data = data_padded[:-pad_len]
    return data.decode("utf-8")


def sm4_encrypt_phone(plaintext_phone: str) -> str:
    return sm4_encrypt_text(plaintext_phone)


def sm4_decrypt_phone(stored: str) -> str:
    return sm4_decrypt_text(stored)
