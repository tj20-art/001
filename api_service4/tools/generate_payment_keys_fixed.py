"""生成支付协议使用的 SM2 十六进制密钥。

目录适配当前项目结构：

PythonProject1/
├─ api_service4/
│  ├─ payment_keys/
│  └─ tools/generate_payment_keys.py
└─ mock_bank/
   └─ payment_keys/

生成后：
- 电商端 api_service4/payment_keys 保存商户私钥、商户公钥、电商私钥、电商公钥
- 银行端 mock_bank/payment_keys 保存商户公钥、电商公钥
"""

import os
import sys
from pathlib import Path


# 当前文件位置：api_service4/tools/generate_payment_keys.py
# ROOT = PythonProject1
# ECOMMERCE_ROOT = PythonProject1/api_service4
# BANK_ROOT = PythonProject1/mock_bank
ECOMMERCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = ECOMMERCE_ROOT.parent
BANK_ROOT = ROOT / "mock_bank"

ECOMMERCE_KEYS = ECOMMERCE_ROOT / "payment_keys"
BANK_KEYS = BANK_ROOT / "payment_keys"


# 确保可以导入电商后端的 payment_crypto.py
# 按你当前项目结构，api_service4 是项目包根目录，运行脚本时把 PythonProject1 加入 sys.path
sys.path.insert(0, str(ROOT))

try:
    from api_service4.app.services.payment_crypto import generate_sm2_keypair
except ModuleNotFoundError:
    # 兼容在 api_service4 目录内直接运行脚本的情况
    sys.path.insert(0, str(ECOMMERCE_ROOT))
    from app.services.payment_crypto import generate_sm2_keypair


def write_key(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")


def write_env_file(path: Path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    merchant = generate_sm2_keypair()
    ecommerce = generate_sm2_keypair()

    # 一、商户签名密钥对
    # 电商端用 merchant_private.key 对支付请求签名
    # 银行端用 merchant_public.key 验签
    write_key(ECOMMERCE_KEYS / "merchant_private.key", merchant["private_key"])
    write_key(ECOMMERCE_KEYS / "merchant_public.key", merchant["public_key"])
    write_key(BANK_KEYS / "merchant_public.key", merchant["public_key"])

    # 二、电商数字信封密钥对
    # 银行端用 ecommerce_public.key 加密支付结果
    # 电商端用 ecommerce_private.key 解密支付结果
    write_key(ECOMMERCE_KEYS / "ecommerce_private.key", ecommerce["private_key"])
    write_key(ECOMMERCE_KEYS / "ecommerce_public.key", ecommerce["public_key"])
    write_key(BANK_KEYS / "ecommerce_public.key", ecommerce["public_key"])

    # 可选：写入环境变量示例文件。
    # 如果你不加载 .env，也没关系；两个后端默认会读取各自当前工作目录下的 ./payment_keys。
    env_ecommerce = ECOMMERCE_ROOT / ".env.ecommerce.payment"
    write_env_file(
        env_ecommerce,
        [
            f"PAYMENT_KEYS_DIR={ECOMMERCE_KEYS}",
            "PAYMENT_MERCHANT_ID=MERCHANT_1001",
            "PAYMENT_BANK_PAY_URL=http://127.0.0.1:8080/pay",
            "ECOMMERCE_BACKEND_BASE_URL=http://127.0.0.1:2333",
            "ECOMMERCE_FRONTEND_BASE_URL=http://127.0.0.1:8081/#/pay-result",
        ],
    )

    env_bank = BANK_ROOT / ".env.mock_bank.payment"
    write_env_file(
        env_bank,
        [
            f"PAYMENT_KEYS_DIR={BANK_KEYS}",
            "BANK_MERCHANT_ID=MERCHANT_1001",
            "BANK_PORT=8080",
            "BANK_TIME_WINDOW_SECONDS=300",
        ],
    )

    print("[OK] 支付密钥已生成")
    print(f"[OK] 电商端密钥目录: {ECOMMERCE_KEYS}")
    print(f"[OK] 银行端密钥目录: {BANK_KEYS}")
    print("")
    print("[电商端文件]")
    print(f"  {ECOMMERCE_KEYS / 'merchant_private.key'}")
    print(f"  {ECOMMERCE_KEYS / 'merchant_public.key'}")
    print(f"  {ECOMMERCE_KEYS / 'ecommerce_private.key'}")
    print(f"  {ECOMMERCE_KEYS / 'ecommerce_public.key'}")
    print("")
    print("[银行端文件]")
    print(f"  {BANK_KEYS / 'merchant_public.key'}")
    print(f"  {BANK_KEYS / 'ecommerce_public.key'}")
    print("")
    print("[OK] 环境变量示例文件")
    print(f"  {env_ecommerce}")
    print(f"  {env_bank}")


if __name__ == "__main__":
    main()
