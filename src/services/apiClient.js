import axios from 'axios'
import store from '@/store'
import router from '@/router'
import { getAccessToken, getRefreshToken, removeAllTokens } from '@/utils/tokenManager'
import { handleApiError } from '@/utils/errorHandler'
import { openSecureResponse, resetSecureRequestForRetry, sealSecureRequest } from '@/utils/secureTunnel'

const apiClient = axios.create({
  baseURL: process.env.VUE_APP_API_BASE_URL || 'https://127.0.0.1:2333',
  timeout: 15000
})

let isRefreshing = false
let pendingRequests = []

const processPendingRequests = (error, token = null) => {
  pendingRequests.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  pendingRequests = []
}

const forceLogout = () => {
  removeAllTokens()
  store.commit('authModule/LOGOUT')
  if (router.currentRoute.path !== '/user-login') {
    router.push('/user-login')
  }
}

apiClient.interceptors.request.use(
  async (config) => {
    const token = getAccessToken()
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
    if (error.response) {
      try {
        error.response = openSecureResponse(error.response)
      } catch (decryptError) {
        handleApiError(decryptError)
        return Promise.reject(decryptError)
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

    const originalRequest = error.config || {}
    const status = error.response && error.response.status
    const hasRefreshToken = !!getRefreshToken()
    const isRefreshRequest = originalRequest.url && originalRequest.url.includes('/api/v1/auth/refresh')

    if (status === 401 && !originalRequest._retry && !isRefreshRequest && hasRefreshToken) {
      originalRequest._retry = true

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingRequests.push({ resolve, reject })
        }).then((newToken) => {
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          resetSecureRequestForRetry(originalRequest)
          return apiClient(originalRequest)
        })
      }

      isRefreshing = true
      try {
        const newAccessToken = await store.dispatch('authModule/refreshToken')
        processPendingRequests(null, newAccessToken)
        originalRequest.headers = originalRequest.headers || {}
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
        resetSecureRequestForRetry(originalRequest)
        return apiClient(originalRequest)
      } catch (refreshError) {
        processPendingRequests(refreshError, null)
        forceLogout()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    if (status === 401) {
      forceLogout()
    }

    handleApiError(error)
    return Promise.reject(error)
  }
)

export default apiClient
