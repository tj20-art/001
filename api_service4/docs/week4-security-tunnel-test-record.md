# 第 4 周应用层安全隧道测试记录

## 1. 测试信息

| 项目 | 内容 |
| --- | --- |
| 测试日期 | 2026-09-17 |
| 测试环境 | Windows，Python 3.11.5，Node.js v25.2.1，npm 11.19.1，MySQL |
| 后端地址 | `https://127.0.0.1:2333` |
| 测试接口 | `POST /api/v1/users/register` |
| 协议版本 | `1` |
| 算法 | SM2（C1C2C3）封装 SM4 Key，SM4-GCM 加密 JSON Body |
| 时间窗 | 当前时间前后 120 秒 |
| 测试数据 | 故意缺少注册必填字段的无效负载，不创建用户、不修改商品或订单 |

## 2. 测试目标

验证安全信封的正常解密、响应加密、密文完整性、AAD 完整性、时间窗、防重放和每请求随机数策略。测试不仅检查 HTTP 状态码，还检查后端返回的 `details.reason`，防止其他业务错误被误判为安全控制生效。

## 3. 执行步骤

在项目根目录启动后端：

```powershell
.\venv\Scripts\python.exe -m api_service4.run
```

在前端目录执行真实端到端测试：

```powershell
cd api-service4-frontend
npm run test:tunnel-live
```

执行密码算法向量测试：

```powershell
npm run test:crypto
```

回到项目根目录执行后端回归测试：

```powershell
.\venv\Scripts\python.exe -m pytest api_service4\tests --no-header --no-summary -q
```

## 4. 失败场景与实际结果

| 编号 | 场景与操作 | 预期结果 | 2026-09-17 实际结果 | 结论 |
| --- | --- | --- | --- | --- |
| T-01 | 正常安全信封携带无效业务负载 | 后端返回加密业务错误响应，客户端能解密 | 收到带 `X-Secure-Response: 1` 的响应并成功解密 | 通过 |
| T-02 | 原样再次发送已经成功消费的信封 | `409 replay_detected` | `409 replay_detected` | 通过 |
| T-03 | 修改 `ciphertext` 最后一个十六进制字符 | `400 invalid_tag` | `400 invalid_tag` | 通过 |
| T-04 | 修改受 AAD 保护的 `request_id`，不重新计算 Tag | `400 invalid_tag` | `400 invalid_tag` | 通过 |
| T-05 | 构造密码学格式正确、但早于服务器时间 180 秒的信封 | `408 expired_timestamp` | `408 expired_timestamp` | 通过 |
| T-06 | 连续生成两个正常信封 | Key、Encrypted Key、IV、Nonce、Request ID 均不同 | 五项全部不同 | 通过 |
| T-07 | SM4 官方标准向量 | 密文等于 `681edf34d206965e86b3e94f536e4246` | 完全一致 | 通过 |
| T-08 | 执行全部后端自动化测试 | 全部通过 | `8 passed in 0.39s` | 通过 |

## 5. 端到端测试原始输出

```json
{
  "protocolVersion": "1",
  "encryptedResponseDecrypted": true,
  "replayRejected": {
    "status": 409,
    "reason": "replay_detected"
  },
  "ciphertextTamperRejected": {
    "status": 400,
    "reason": "invalid_tag"
  },
  "aadTamperRejected": {
    "status": 400,
    "reason": "invalid_tag"
  },
  "expiredTimestampRejected": {
    "status": 408,
    "reason": "expired_timestamp"
  },
  "perRequestRandomValuesChanged": [
    "encrypted_key",
    "iv",
    "nonce",
    "request_id",
    "session_key"
  ]
}
```

## 6. 结果判定

本次自动化验证覆盖了第 4 周要求中的密文篡改、AAD 篡改、重放、过期请求和每请求随机值变化。所有场景均达到预期，且完整后端回归测试没有出现失败。

测试脚本为了访问本机 Flask 自动生成的自签名开发证书，仅在该 Node.js 测试进程内设置 `NODE_TLS_REJECT_UNAUTHORIZED=0`。浏览器和生产环境不得关闭证书验证，应用层安全信封也不得替代 HTTPS。

## 7. 复验说明

- 复验前确保 MySQL 已启动、数据库配置正确，且 2333 端口未被占用。
- 每次复验都必须重新运行命令，不应只提交本文件中的历史结果。
- `baseline-browser-mapping` 和 `caniuse-lite` 的过期提示是前端兼容数据维护警告，不影响本次密码算法与安全信封测试结论。
- 抓包证据应另行保存为浏览器 Network 截图或 HAR，用于证明请求 Body 中不存在业务明文。
