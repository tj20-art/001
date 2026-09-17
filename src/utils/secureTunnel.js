/* global BigInt */
import axios from 'axios'
import { sm2 } from 'sm-crypto'

const VERSION = '1'
const ALGORITHM = 'SM2+SM4-GCM'
const RESPONSE_ALGORITHM = 'SM4-GCM'
const encoder = new TextEncoder()
const decoder = new TextDecoder()

const SBOX = [
  0xd6, 0x90, 0xe9, 0xfe, 0xcc, 0xe1, 0x3d, 0xb7, 0x16, 0xb6, 0x14, 0xc2, 0x28, 0xfb, 0x2c, 0x05, 0x2b, 0x67, 0x9a,
  0x76, 0x2a, 0xbe, 0x04, 0xc3, 0xaa, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99, 0x9c, 0x42, 0x50, 0xf4, 0x91, 0xef,
  0x98, 0x7a, 0x33, 0x54, 0x0b, 0x43, 0xed, 0xcf, 0xac, 0x62, 0xe4, 0xb3, 0x1c, 0xa9, 0xc9, 0x08, 0xe8, 0x95, 0x80,
  0xdf, 0x94, 0xfa, 0x75, 0x8f, 0x3f, 0xa6, 0x47, 0x07, 0xa7, 0xfc, 0xf3, 0x73, 0x17, 0xba, 0x83, 0x59, 0x3c, 0x19,
  0xe6, 0x85, 0x4f, 0xa8, 0x68, 0x6b, 0x81, 0xb2, 0x71, 0x64, 0xda, 0x8b, 0xf8, 0xeb, 0x0f, 0x4b, 0x70, 0x56, 0x9d,
  0x35, 0x1e, 0x24, 0x0e, 0x5e, 0x63, 0x58, 0xd1, 0xa2, 0x25, 0x22, 0x7c, 0x3b, 0x01, 0x21, 0x78, 0x87, 0xd4, 0x00,
  0x46, 0x57, 0x9f, 0xd3, 0x27, 0x52, 0x4c, 0x36, 0x02, 0xe7, 0xa0, 0xc4, 0xc8, 0x9e, 0xea, 0xbf, 0x8a, 0xd2, 0x40,
  0xc7, 0x38, 0xb5, 0xa3, 0xf7, 0xf2, 0xce, 0xf9, 0x61, 0x15, 0xa1, 0xe0, 0xae, 0x5d, 0xa4, 0x9b, 0x34, 0x1a, 0x55,
  0xad, 0x93, 0x32, 0x30, 0xf5, 0x8c, 0xb1, 0xe3, 0x1d, 0xf6, 0xe2, 0x2e, 0x82, 0x66, 0xca, 0x60, 0xc0, 0x29, 0x23,
  0xab, 0x0d, 0x53, 0x4e, 0x6f, 0xd5, 0xdb, 0x37, 0x45, 0xde, 0xfd, 0x8e, 0x2f, 0x03, 0xff, 0x6a, 0x72, 0x6d, 0x6c,
  0x5b, 0x51, 0x8d, 0x1b, 0xaf, 0x92, 0xbb, 0xdd, 0xbc, 0x7f, 0x11, 0xd9, 0x5c, 0x41, 0x1f, 0x10, 0x5a, 0xd8, 0x0a,
  0xc1, 0x31, 0x88, 0xa5, 0xcd, 0x7b, 0xbd, 0x2d, 0x74, 0xd0, 0x12, 0xb8, 0xe5, 0xb4, 0xb0, 0x89, 0x69, 0x97, 0x4a,
  0x0c, 0x96, 0x77, 0x7e, 0x65, 0xb9, 0xf1, 0x09, 0xc5, 0x6e, 0xc6, 0x84, 0x18, 0xf0, 0x7d, 0xec, 0x3a, 0xdc, 0x4d,
  0x20, 0x79, 0xee, 0x5f, 0x3e, 0xd7, 0xcb, 0x39, 0x48
]

const FK = [0xa3b1bac6, 0x56aa3350, 0x677d9197, 0xb27022dc]
const CK = [
  0x00070e15, 0x1c232a31, 0x383f464d, 0x545b6269, 0x70777e85, 0x8c939aa1, 0xa8afb6bd, 0xc4cbd2d9, 0xe0e7eef5,
  0xfc030a11, 0x181f262d, 0x343b4249, 0x50575e65, 0x6c737a81, 0x888f969d, 0xa4abb2b9, 0xc0c7ced5, 0xdce3eaf1,
  0xf8ff060d, 0x141b2229, 0x30373e45, 0x4c535a61, 0x686f767d, 0x848b9299, 0xa0a7aeb5, 0xbcc3cad1, 0xd8dfe6ed,
  0xf4fb0209, 0x10171e25, 0x2c333a41, 0x484f565d, 0x646b7279
]

const rotateLeft = (value, bits) => ((value << bits) | (value >>> (32 - bits))) >>> 0

const substituteWord = (word) =>
  ((SBOX[(word >>> 24) & 0xff] << 24) |
    (SBOX[(word >>> 16) & 0xff] << 16) |
    (SBOX[(word >>> 8) & 0xff] << 8) |
    SBOX[word & 0xff]) >>>
  0

const roundTransform = (word) => {
  const substituted = substituteWord(word)
  return (
    (substituted ^
      rotateLeft(substituted, 2) ^
      rotateLeft(substituted, 10) ^
      rotateLeft(substituted, 18) ^
      rotateLeft(substituted, 24)) >>>
    0
  )
}

const keyTransform = (word) => {
  const substituted = substituteWord(word)
  return (substituted ^ rotateLeft(substituted, 13) ^ rotateLeft(substituted, 23)) >>> 0
}

const readWord = (bytes, offset) =>
  ((bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3]) >>> 0

const writeWord = (bytes, offset, word) => {
  bytes[offset] = (word >>> 24) & 0xff
  bytes[offset + 1] = (word >>> 16) & 0xff
  bytes[offset + 2] = (word >>> 8) & 0xff
  bytes[offset + 3] = word & 0xff
}

const expandKey = (key) => {
  if (!(key instanceof Uint8Array) || key.length !== 16) {
    throw new Error('SM4 会话密钥必须为 16 字节')
  }
  const state = new Uint32Array(36)
  const roundKeys = new Uint32Array(32)
  for (let i = 0; i < 4; i += 1) state[i] = (readWord(key, i * 4) ^ FK[i]) >>> 0
  for (let i = 0; i < 32; i += 1) {
    state[i + 4] = (state[i] ^ keyTransform(state[i + 1] ^ state[i + 2] ^ state[i + 3] ^ CK[i])) >>> 0
    roundKeys[i] = state[i + 4]
  }
  return roundKeys
}

const encryptBlock = (block, roundKeys) => {
  const state = new Uint32Array(36)
  for (let i = 0; i < 4; i += 1) state[i] = readWord(block, i * 4)
  for (let i = 0; i < 32; i += 1) {
    state[i + 4] = (state[i] ^ roundTransform(state[i + 1] ^ state[i + 2] ^ state[i + 3] ^ roundKeys[i])) >>> 0
  }
  const result = new Uint8Array(16)
  for (let i = 0; i < 4; i += 1) writeWord(result, i * 4, state[35 - i])
  return result
}

const xorBytes = (left, right) => {
  const result = new Uint8Array(left.length)
  for (let i = 0; i < left.length; i += 1) result[i] = left[i] ^ right[i]
  return result
}

const concatBytes = (...arrays) => {
  const result = new Uint8Array(arrays.reduce((size, item) => size + item.length, 0))
  let offset = 0
  arrays.forEach((item) => {
    result.set(item, offset)
    offset += item.length
  })
  return result
}

const bytesToBigInt = (bytes) => {
  let value = 0n
  for (const byte of bytes) value = (value << 8n) | BigInt(byte)
  return value
}

const bigIntToBytes = (value) => {
  const result = new Uint8Array(16)
  let remaining = value
  for (let i = 15; i >= 0; i -= 1) {
    result[i] = Number(remaining & 0xffn)
    remaining >>= 8n
  }
  return result
}

const multiplyGf128 = (left, right) => {
  const reduction = 0xe1000000000000000000000000000000n
  let product = 0n
  let factor = bytesToBigInt(right)
  const input = bytesToBigInt(left)
  for (let bit = 127; bit >= 0; bit -= 1) {
    if (((input >> BigInt(bit)) & 1n) === 1n) product ^= factor
    factor = (factor & 1n) === 0n ? factor >> 1n : (factor >> 1n) ^ reduction
  }
  return bigIntToBytes(product)
}

const writeUint64 = (target, offset, value) => {
  let remaining = BigInt(value)
  for (let i = 7; i >= 0; i -= 1) {
    target[offset + i] = Number(remaining & 0xffn)
    remaining >>= 8n
  }
}

const ghash = (hashSubKey, aad, ciphertext) => {
  const aadPadding = (16 - (aad.length % 16)) % 16
  const ciphertextPadding = (16 - (ciphertext.length % 16)) % 16
  const lengths = new Uint8Array(16)
  writeUint64(lengths, 0, BigInt(aad.length) * 8n)
  writeUint64(lengths, 8, BigInt(ciphertext.length) * 8n)
  const input = concatBytes(aad, new Uint8Array(aadPadding), ciphertext, new Uint8Array(ciphertextPadding), lengths)
  let accumulator = new Uint8Array(16)
  for (let offset = 0; offset < input.length; offset += 16) {
    accumulator = multiplyGf128(xorBytes(accumulator, input.slice(offset, offset + 16)), hashSubKey)
  }
  return accumulator
}

const incrementCounter = (counter) => {
  const result = counter.slice()
  for (let i = 15; i >= 12; i -= 1) {
    result[i] = (result[i] + 1) & 0xff
    if (result[i] !== 0) break
  }
  return result
}

const sm4GcmCrypt = (input, key, iv) => {
  if (iv.length !== 12) throw new Error('SM4-GCM IV 必须为 12 字节')
  const roundKeys = expandKey(key)
  const initialCounter = concatBytes(iv, new Uint8Array([0, 0, 0, 1]))
  let counter = initialCounter
  const output = new Uint8Array(input.length)
  for (let offset = 0; offset < input.length; offset += 16) {
    counter = incrementCounter(counter)
    const stream = encryptBlock(counter, roundKeys)
    const blockLength = Math.min(16, input.length - offset)
    for (let i = 0; i < blockLength; i += 1) output[offset + i] = input[offset + i] ^ stream[i]
  }
  return { output, roundKeys, initialCounter }
}

const sm4GcmEncrypt = (plaintext, key, iv, aad) => {
  const { output: ciphertext, roundKeys, initialCounter } = sm4GcmCrypt(plaintext, key, iv)
  const tag = xorBytes(
    encryptBlock(initialCounter, roundKeys),
    ghash(encryptBlock(new Uint8Array(16), roundKeys), aad, ciphertext)
  )
  return { ciphertext, tag }
}

const sm4GcmDecrypt = (ciphertext, key, iv, aad, suppliedTag) => {
  const roundKeys = expandKey(key)
  const initialCounter = concatBytes(iv, new Uint8Array([0, 0, 0, 1]))
  const expectedTag = xorBytes(
    encryptBlock(initialCounter, roundKeys),
    ghash(encryptBlock(new Uint8Array(16), roundKeys), aad, ciphertext)
  )
  let difference = suppliedTag.length ^ expectedTag.length
  for (let i = 0; i < Math.min(suppliedTag.length, expectedTag.length); i += 1)
    difference |= suppliedTag[i] ^ expectedTag[i]
  if (difference !== 0) throw new Error('安全响应完整性校验失败')
  return sm4GcmCrypt(ciphertext, key, iv).output
}

const toHex = (bytes) => Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')

const fromHex = (hex, fieldName) => {
  const normalized = String(hex || '').trim()
  if (!normalized || normalized.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(normalized)) {
    throw new Error(`${fieldName} 格式错误`)
  }
  const result = new Uint8Array(normalized.length / 2)
  for (let i = 0; i < result.length; i += 1) result[i] = parseInt(normalized.slice(i * 2, i * 2 + 2), 16)
  return result
}

const randomBytes = (length) => {
  const result = new Uint8Array(length)
  window.crypto.getRandomValues(result)
  return result
}

const randomId = (length = 16) => toHex(randomBytes(length))

const requestAad = (method, path, timestamp, nonce, requestId) =>
  encoder.encode(`${String(method).toUpperCase()}\n${path}\n${timestamp}\n${nonce}\n${requestId}`)

const responseAad = (requestId) => encoder.encode(`RESPONSE\n${requestId}`)

let publicKeyPromise = null

const getTunnelPublicKey = async () => {
  if (!publicKeyPromise) {
    const baseUrl = process.env.VUE_APP_API_BASE_URL || 'https://127.0.0.1:2333'
    publicKeyPromise = axios
      .get(`${baseUrl}/api/v1/security/public-key`, { timeout: 10000 })
      .then((response) => response.data && response.data.data && response.data.data.public_key)
      .then((publicKey) => {
        if (!publicKey) throw new Error('服务端未返回安全隧道公钥')
        return publicKey.length === 128 ? `04${publicKey}` : publicKey
      })
      .catch((error) => {
        publicKeyPromise = null
        throw error
      })
  }
  return publicKeyPromise
}

const isJsonObject = (value) =>
  value !== null && typeof value === 'object' && !(value instanceof FormData) && !(value instanceof Blob)

const shouldEncrypt = (config) => {
  const method = String(config.method || 'get').toLowerCase()
  return ['post', 'put', 'patch', 'delete'].includes(method) && isJsonObject(config.data)
}

const requestPath = (url) => new URL(url, window.location.origin).pathname

export const sealSecureRequest = async (config) => {
  if (!shouldEncrypt(config)) return config
  if (config._secureEnvelopeSealed) return config

  const publicKey = await getTunnelPublicKey()
  const key = randomBytes(16)
  const iv = randomBytes(12)
  const nonce = randomId(16)
  const requestId = randomId(16)
  const timestamp = Date.now()
  const method = String(config.method || 'post').toUpperCase()
  const path = requestPath(config.url)
  const plaintext = encoder.encode(JSON.stringify(config.data))
  const { ciphertext, tag } = sm4GcmEncrypt(plaintext, key, iv, requestAad(method, path, timestamp, nonce, requestId))

  config._secureOriginalData = config.data
  config._secureEnvelopeSealed = true
  config._secureContext = { key, requestId }
  config.data = {
    version: VERSION,
    algorithm: ALGORITHM,
    // gmssl 服务端使用 C1C2C3（cipherMode=0）解密格式。
    encrypted_key: sm2.doEncrypt(toHex(key), publicKey, 0),
    iv: toHex(iv),
    ciphertext: toHex(ciphertext),
    tag: toHex(tag),
    nonce,
    timestamp,
    request_id: requestId
  }
  config.headers = config.headers || {}
  config.headers['Content-Type'] = 'application/json'
  config.headers['X-Secure-Envelope'] = VERSION
  return config
}

export const openSecureResponse = (response) => {
  if (!response || !response.headers || response.headers['x-secure-response'] !== VERSION) return response
  const context = response.config && response.config._secureContext
  const envelope = response.data
  if (!context || !envelope || envelope.algorithm !== RESPONSE_ALGORITHM || envelope.request_id !== context.requestId) {
    throw new Error('安全响应与原请求不匹配')
  }
  const plaintext = sm4GcmDecrypt(
    fromHex(envelope.ciphertext, 'ciphertext'),
    context.key,
    fromHex(envelope.iv, 'iv'),
    responseAad(context.requestId),
    fromHex(envelope.tag, 'tag')
  )
  response.data = JSON.parse(decoder.decode(plaintext))
  return response
}

export const resetSecureRequestForRetry = (config) => {
  if (!config) return config
  if (Object.prototype.hasOwnProperty.call(config, '_secureOriginalData')) config.data = config._secureOriginalData
  delete config._secureEnvelopeSealed
  delete config._secureContext
  if (config.headers) delete config.headers['X-Secure-Envelope']
  return config
}

export const __test__ = {
  encryptBlock,
  expandKey,
  fromHex,
  requestAad,
  sm4GcmDecrypt,
  sm4GcmEncrypt,
  toHex
}
