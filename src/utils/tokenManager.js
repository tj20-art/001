const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

const getStorage = () => window.sessionStorage

const decodePayload = (token) => {
  const parts = (token || '').split('.')
  if (parts.length < 2) return null

  try {
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(atob(padded))
  } catch (error) {
    return null
  }
}

export const setAccessToken = (token) => {
  if (!token) return
  getStorage().setItem(ACCESS_TOKEN_KEY, token)
}

export const getAccessToken = () => getStorage().getItem(ACCESS_TOKEN_KEY)

export const removeAccessToken = () => {
  getStorage().removeItem(ACCESS_TOKEN_KEY)
}

export const setRefreshToken = (token) => {
  if (!token) return
  getStorage().setItem(REFRESH_TOKEN_KEY, token)
}

export const getRefreshToken = () => getStorage().getItem(REFRESH_TOKEN_KEY)

export const removeRefreshToken = () => {
  getStorage().removeItem(REFRESH_TOKEN_KEY)
}

export const removeAllTokens = () => {
  removeAccessToken()
  removeRefreshToken()
}

export const isTokenExpired = (token) => {
  if (!token) return true

  try {
    const payload = decodePayload(token)
    return !payload || !payload.exp || payload.exp * 1000 < Date.now()
  } catch (error) {
    return true
  }
}
