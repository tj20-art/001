import axios from 'axios'
import store from '@/store'
import router from '@/router'
import { getAccessToken, getRefreshToken } from '@/utils/tokenManager'
import { handleApiError } from '@/utils/errorHandler'
import { openSecureResponse, resetSecureRequestForRetry, sealSecureRequest } from '@/utils/secureTunnel'

const apiClient = axios.create({
  baseURL: process.env.VUE_APP_API_BASE_URL || 'https://127.0.0.1:2333',
  timeout: 15000
})

let pendingRefresh = null

const refreshSession = (version) => {
  if (pendingRefresh?.version !== version) {
    const promise = store.dispatch('authModule/refreshToken').finally(() => {
      if (pendingRefresh?.version === version) pendingRefresh = null
    })
    pendingRefresh = { version, promise }
  }
  return pendingRefresh.promise
}

const expireSession = (version, error) => {
  if (store.state.authModule.sessionVersion !== version) return
  store.commit('authModule/LOGOUT')
  handleApiError(error)
  const route = router.currentRoute.value
  if (route.path !== '/user-login') {
    const redirect = route.meta.requiresAuth || route.meta.restoreAuth ? route.fullPath : undefined
    router.replace({ path: '/user-login', query: { redirect } }).catch(() => {})
  }
}

apiClient.interceptors.request.use(
  async (config) => {
    const { sessionVersion } = store.state.authModule
    if (config._retry && config._sessionVersion !== sessionVersion) {
      throw new axios.CanceledError()
    }

    const token = getAccessToken()
    config._sessionVersion = sessionVersion
    config._accessToken = token
    if (token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${token}`
    }
    return sealSecureRequest(config)
  },
  (error) => Promise.reject(error)
)

apiClient.interceptors.response.use(
  (rawResponse) => {
    const response = openSecureResponse(rawResponse)
    const isBlob = response.config && response.config.responseType === 'blob'
    const hasAttachment = !!(response.headers && response.headers['content-disposition'])
    if (isBlob || hasAttachment) {
      return response
    }
    return response.data
  },
  async (error) => {
    if (axios.isCancel(error)) throw error

    const originalRequest = error.config || {}
    const isRefreshRequest = originalRequest.url === '/api/v1/auth/refresh'
    if (error.response) {
      try {
        error.response = openSecureResponse(error.response)
      } catch (decryptError) {
        if (!isRefreshRequest && !originalRequest.silentError) handleApiError(decryptError)
        throw decryptError
      }
    }

    if (
      error.response &&
      error.response.data instanceof Blob &&
      error.response.data.type &&
      error.response.data.type.includes('application/json')
    ) {
      try {
        const text = await error.response.data.text()
        error.response.data = JSON.parse(text)
      } catch (blobError) {
        // ignore blob parse failure
      }
    }

    // The caller handles refresh failures for the entire session.
    if (isRefreshRequest) throw error

    const isAuthRequest = originalRequest.url?.startsWith('/api/v1/auth/')
    if (error.response?.status !== 401 || isAuthRequest || !originalRequest._accessToken) {
      if (!originalRequest.silentError) handleApiError(error)
      throw error
    }

    const version = originalRequest._sessionVersion
    if (version !== store.state.authModule.sessionVersion) throw error

    const reason = error.response.data?.details?.reason
    if (reason === 'auth_version_changed' || originalRequest._retry || !getRefreshToken()) {
      expireSession(version, error)
      throw error
    }

    try {
      if (originalRequest._accessToken === getAccessToken()) await refreshSession(version)
    } catch (refreshError) {
      expireSession(version, error)
      throw refreshError
    }

    if (version !== store.state.authModule.sessionVersion) throw error
    originalRequest._retry = true
    resetSecureRequestForRetry(originalRequest)
    return apiClient(originalRequest)
  }
)

export default apiClient
