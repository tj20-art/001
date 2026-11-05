import apiClient from './apiClient'

export const loginByCert = (formData) => {
  return apiClient({
    url: '/api/v1/auth/login',
    method: 'POST',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export const refreshTokenApi = (data) => {
  return apiClient({
    url: '/api/v1/auth/refresh',
    method: 'POST',
    data
  })
}

export const enrollMfaApi = (data) => {
  return apiClient({
    url: '/api/v1/auth/mfa/enroll',
    method: 'POST',
    data
  })
}

export const verifyMfaApi = (data) => {
  return apiClient({
    url: '/api/v1/auth/mfa/verify',
    method: 'POST',
    data
  })
}
