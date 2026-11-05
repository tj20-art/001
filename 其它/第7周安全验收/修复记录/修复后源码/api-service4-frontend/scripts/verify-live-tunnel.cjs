const fs = require('fs')
const Module = require('module')
const path = require('path')
const babel = require('@babel/core')
const axios = require('axios')
const { sm2 } = require('sm-crypto')

process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'
process.env.VUE_APP_API_BASE_URL = process.env.TUNNEL_TEST_BASE_URL || 'https://127.0.0.1:2333'
global.window = {
  crypto: require('crypto').webcrypto,
  location: { origin: process.env.VUE_APP_API_BASE_URL }
}

const sourcePath = path.resolve(__dirname, '../src/utils/secureTunnel.js')
const source = fs.readFileSync(sourcePath, 'utf8')
const transformed = babel.transformSync(source, {
  filename: sourcePath,
  plugins: [require.resolve('@babel/plugin-transform-modules-commonjs')]
}).code
const cryptoModule = new Module(sourcePath, module)
cryptoModule.filename = sourcePath
cryptoModule.paths = Module._nodeModulePaths(path.dirname(sourcePath))
cryptoModule._compile(transformed, sourcePath)

const { openSecureResponse, sealSecureRequest, __test__ } = cryptoModule.exports
const { requestAad, sm4GcmEncrypt, toHex } = __test__
const endpoint = `${process.env.VUE_APP_API_BASE_URL}/api/v1/users/register`

const send = (config) => axios.request({ ...config, validateStatus: () => true })
const clone = (value) => JSON.parse(JSON.stringify(value))
const randomBytes = (length) => new Uint8Array(require('crypto').randomBytes(length))
const randomHex = (length) => toHex(randomBytes(length))

const envelopeRequest = (sealed, data = sealed.data) => ({
  method: sealed.method,
  url: sealed.url,
  data: clone(data),
  headers: { ...sealed.headers },
  _secureContext: sealed._secureContext
})

const requireFailure = (response, expectedStatus, expectedReason, scenario) => {
  if (response.status !== expectedStatus || response.data?.details?.reason !== expectedReason) {
    throw new Error(`${scenario}未按预期拒绝: HTTP ${response.status} ${JSON.stringify(response.data)}`)
  }
}

const buildEnvelope = ({ publicKey, timestamp, payload }) => {
  const key = randomBytes(16)
  const iv = randomBytes(12)
  const nonce = randomHex(16)
  const requestId = randomHex(16)
  const plaintext = new TextEncoder().encode(JSON.stringify(payload))
  const encrypted = sm4GcmEncrypt(
    plaintext,
    key,
    iv,
    requestAad('POST', '/api/v1/users/register', timestamp, nonce, requestId)
  )
  const normalizedPublicKey = publicKey.length === 128 ? `04${publicKey}` : publicKey
  return {
    version: '1',
    algorithm: 'SM2+SM4-GCM',
    encrypted_key: sm2.doEncrypt(toHex(key), normalizedPublicKey, 0),
    iv: toHex(iv),
    ciphertext: toHex(encrypted.ciphertext),
    tag: toHex(encrypted.tag),
    nonce,
    timestamp,
    request_id: requestId
  }
}

async function main() {
  const sealed = await sealSecureRequest({
    method: 'post',
    url: endpoint,
    data: { username: 'x' }
  })
  const envelope = clone(sealed.data)
  const first = await send(envelopeRequest(sealed, envelope))
  if (first.status < 400 || first.status >= 500 || first.headers['x-secure-response'] !== '1') {
    throw new Error(`首次安全请求响应异常: HTTP ${first.status}`)
  }
  const opened = openSecureResponse(first)
  if (!opened.data || opened.data.code !== first.status) throw new Error('安全响应解密失败')

  const replay = await send(envelopeRequest(sealed, envelope))
  requireFailure(replay, 409, 'replay_detected', '重放请求')

  const tampered = await sealSecureRequest({ method: 'post', url: endpoint, data: { username: 'x' } })
  const last = tampered.data.ciphertext.slice(-1)
  tampered.data.ciphertext = `${tampered.data.ciphertext.slice(0, -1)}${last === '0' ? '1' : '0'}`
  const tamperResponse = await send(envelopeRequest(tampered))
  requireFailure(tamperResponse, 400, 'invalid_tag', '密文篡改请求')

  const aadTampered = await sealSecureRequest({ method: 'post', url: endpoint, data: { username: 'x' } })
  aadTampered.data.request_id = randomHex(16)
  const aadTamperResponse = await send(envelopeRequest(aadTampered))
  requireFailure(aadTamperResponse, 400, 'invalid_tag', 'AAD 篡改请求')

  const publicKeyResponse = await axios.get(`${process.env.VUE_APP_API_BASE_URL}/api/v1/security/public-key`)
  const publicKey = publicKeyResponse.data?.data?.public_key
  if (!publicKey) throw new Error('无法获取服务端安全隧道公钥')
  const expiredEnvelope = buildEnvelope({
    publicKey,
    timestamp: Date.now() - 180000,
    payload: { username: 'x' }
  })
  const expiredResponse = await send({
    method: 'post',
    url: endpoint,
    data: expiredEnvelope,
    headers: { 'Content-Type': 'application/json', 'X-Secure-Envelope': '1' }
  })
  requireFailure(expiredResponse, 408, 'expired_timestamp', '过期时间戳请求')

  const randomA = await sealSecureRequest({ method: 'post', url: endpoint, data: { username: 'x' } })
  const randomB = await sealSecureRequest({ method: 'post', url: endpoint, data: { username: 'x' } })
  const uniquenessFields = ['encrypted_key', 'iv', 'nonce', 'request_id']
  const duplicateFields = uniquenessFields.filter((field) => randomA.data[field] === randomB.data[field])
  const sameSessionKey = toHex(randomA._secureContext.key) === toHex(randomB._secureContext.key)
  if (duplicateFields.length || sameSessionKey) {
    throw new Error(`随机性检查失败: ${[...duplicateFields, ...(sameSessionKey ? ['session_key'] : [])].join(', ')}`)
  }

  process.stdout.write(
    `${JSON.stringify(
      {
        protocolVersion: '1',
        encryptedResponseDecrypted: true,
        replayRejected: { status: replay.status, reason: replay.data.details.reason },
        ciphertextTamperRejected: { status: tamperResponse.status, reason: tamperResponse.data.details.reason },
        aadTamperRejected: { status: aadTamperResponse.status, reason: aadTamperResponse.data.details.reason },
        expiredTimestampRejected: { status: expiredResponse.status, reason: expiredResponse.data.details.reason },
        perRequestRandomValuesChanged: [...uniquenessFields, 'session_key']
      },
      null,
      2
    )}\n`
  )
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`)
  process.exitCode = 1
})
