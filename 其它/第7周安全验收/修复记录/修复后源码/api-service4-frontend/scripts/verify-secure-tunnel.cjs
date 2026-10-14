const fs = require('fs')
const Module = require('module')
const path = require('path')
const babel = require('@babel/core')

global.window = {
  crypto: require('crypto').webcrypto,
  location: { origin: 'http://localhost' }
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

const {
  encryptBlock,
  expandKey,
  fromHex,
  normalizeSecurePayload,
  requestAad,
  shouldEncrypt,
  sm4GcmDecrypt,
  sm4GcmEncrypt,
  toHex
} = cryptoModule.exports.__test__

if (!shouldEncrypt({ method: 'POST' }) || !shouldEncrypt({ method: 'DELETE', data: undefined })) {
  throw new Error('无 Body 的写请求没有进入安全隧道')
}
if (shouldEncrypt({ method: 'GET' }) || shouldEncrypt({ method: 'POST', data: new FormData() })) {
  throw new Error('安全隧道错误处理了只读请求或 multipart 请求')
}
if (JSON.stringify(normalizeSecurePayload(undefined)) !== '{}') {
  throw new Error('无 Body 的写请求没有被规范化为空 JSON 对象')
}

const key = fromHex('0123456789abcdeffedcba9876543210', 'key')
const knownPlaintext = fromHex('0123456789abcdeffedcba9876543210', 'plaintext')
const knownCiphertext = toHex(encryptBlock(knownPlaintext, expandKey(key)))
if (knownCiphertext !== '681edf34d206965e86b3e94f536e4246') {
  throw new Error(`SM4 标准向量失败: ${knownCiphertext}`)
}

const iv = fromHex('000102030405060708090a0b', 'iv')
const aad = requestAad('POST', '/api/v1/users/register', 1700000000000, 'nonce-test', 'request-test')
const plaintext = new TextEncoder().encode(JSON.stringify({ username: 'interop-test', amount: 100 }))
const encrypted = sm4GcmEncrypt(plaintext, key, iv, aad)
const decrypted = sm4GcmDecrypt(encrypted.ciphertext, key, iv, aad, encrypted.tag)
if (new TextDecoder().decode(decrypted) !== new TextDecoder().decode(plaintext)) {
  throw new Error('SM4-GCM 往返测试失败')
}

process.stdout.write(JSON.stringify({
  knownCiphertext,
  key: toHex(key),
  iv: toHex(iv),
  aad: toHex(aad),
  plaintext: toHex(plaintext),
  ciphertext: toHex(encrypted.ciphertext),
  tag: toHex(encrypted.tag)
}))
