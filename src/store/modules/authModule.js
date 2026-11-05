import { enrollMfaApi, loginByCert as loginByCertApi, refreshTokenApi, verifyMfaApi } from '@/services/authService'
import {
  setAccessToken,
  getAccessToken,
  removeAllTokens,
  setRefreshToken,
  getRefreshToken,
  isTokenExpired
} from '@/utils/tokenManager'

const decodeJwtPayload = (token) => {
  if (!token) return null
  try {
    const payloadPart = token.split('.')[1]
    if (!payloadPart) return null
    const normalized = payloadPart.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    const decoded = decodeURIComponent(
      Array.prototype.map.call(atob(padded), (char) => `%${`00${char.charCodeAt(0).toString(16)}`.slice(-2)}`).join('')
    )
    return JSON.parse(decoded)
  } catch (error) {
    return null
  }
}

const normalizeUser = (user, accessToken) => {
  if (user) {
    return {
      ...user,
      id: user.id || user.user_id
    }
  }

  const payload = decodeJwtPayload(accessToken)
  if (!payload) return null

  return {
    id: payload.user_id || payload.id,
    user_id: payload.user_id || payload.id,
    username: payload.username,
    role: payload.role
  }
}

const initialAccessToken = getAccessToken()
const initialRefreshToken = getRefreshToken()

const state = {
  isAuthenticated: !!initialAccessToken && !isTokenExpired(initialAccessToken),
  user: normalizeUser(null, initialAccessToken),
  accessToken: initialAccessToken || null,
  refreshToken: initialRefreshToken || null
}

const mutations = {
  SET_AUTH_DATA(state, { user, accessToken, refreshToken }) {
    const normalizedUser = normalizeUser(user || state.user, accessToken || state.accessToken)

    state.user = normalizedUser || null
    state.accessToken = accessToken || null
    state.refreshToken = refreshToken || null
    state.isAuthenticated = !!state.accessToken

    if (state.accessToken) {
      setAccessToken(state.accessToken)
    }
    if (state.refreshToken) {
      setRefreshToken(state.refreshToken)
    }
    if (!state.accessToken && !state.refreshToken) {
      removeAllTokens()
    }
  },

  SET_ACCESS_TOKEN(state, accessToken) {
    state.accessToken = accessToken || null
    state.isAuthenticated = !!accessToken
    state.user = normalizeUser(state.user, accessToken)
    if (accessToken) {
      setAccessToken(accessToken)
    }
  },

  MERGE_USER(state, userPatch) {
    state.user = normalizeUser({ ...(state.user || {}), ...(userPatch || {}) }, state.accessToken)
  },

  LOGOUT(state) {
    state.isAuthenticated = false
    state.user = null
    state.accessToken = null
    state.refreshToken = null
    removeAllTokens()
  }
}

const actions = {
  async loginByCert({ commit }, { certFile, password }) {
    const formData = new FormData()
    formData.append('certificate', certFile)
    formData.append('password', password)

    const res = await loginByCertApi(formData)
    if (res?.data?.mfa_required) return res
    const rawUser = (res && res.data && res.data.user_info) || null
    const userInfo = normalizeUser(rawUser, res && res.data && res.data.access_token)

    commit('SET_AUTH_DATA', {
      user: userInfo,
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token
    })
    return res
  },

  async completeMfa({ commit }, { mfaToken, code, setupRequired }) {
    const payload = { mfa_token: mfaToken, code }
    const res = setupRequired ? await enrollMfaApi(payload) : await verifyMfaApi(payload)
    const rawUser = (res && res.data && res.data.user_info) || null
    const userInfo = normalizeUser(rawUser, res && res.data && res.data.access_token)
    commit('SET_AUTH_DATA', {
      user: userInfo,
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token
    })
    return res
  },

  async refreshToken({ state, commit }) {
    const currentUser = normalizeUser(state.user, state.accessToken)
    if (!state.refreshToken || !currentUser || !currentUser.id) {
      throw new Error('缺少刷新令牌，请重新登录')
    }

    const res = await refreshTokenApi({
      user_id: currentUser.id,
      refresh_token: state.refreshToken
    })

    if (!res || res.code !== 0 || !res.data || !res.data.access_token) {
      throw new Error((res && res.message) || '刷新令牌失败')
    }

    if (!res.data.refresh_token) {
      throw new Error('服务端未返回轮换后的刷新令牌')
    }

    commit('SET_AUTH_DATA', {
      user: currentUser,
      accessToken: res.data.access_token,
      refreshToken: res.data.refresh_token
    })
    return res.data.access_token
  },

  async initAuthState({ commit, dispatch, state }) {
    const normalizedUser = normalizeUser(state.user, state.accessToken)

    if (state.accessToken && !isTokenExpired(state.accessToken)) {
      commit('SET_AUTH_DATA', {
        user: normalizedUser,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken
      })
      return
    }

    if (state.refreshToken && normalizedUser) {
      try {
        const newAccessToken = await dispatch('refreshToken')
        commit('SET_AUTH_DATA', {
          user: normalizedUser,
          accessToken: newAccessToken,
          refreshToken: state.refreshToken
        })
      } catch (error) {
        commit('LOGOUT')
      }
      return
    }

    commit('LOGOUT')
  }
}

const getters = {
  isAdmin: (state) => state.user && state.user.role === 'admin',
  isMerchant: (state) => state.user && state.user.role === 'merchant',
  isAuditor: (state) => state.user && state.user.role === 'auditor',
  canManageProducts: (state) => state.user && ['merchant', 'admin'].includes(state.user.role),
  canShop: (state) => state.user && state.user.role === 'user',
  userId: (state) => (state.user ? state.user.id : ''),
  accessToken: (state) => state.accessToken,
  refreshToken: (state) => state.refreshToken,
  username: (state) => (state.user ? state.user.username : '')
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
