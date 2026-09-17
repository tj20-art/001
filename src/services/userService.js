import apiClient from './apiClient'

export const register = (userData, options = {}) => {
  const params = {}
  if (options.download) {
    params.download = 1
  }

  return apiClient({
    url: '/api/v1/users/register',
    method: 'POST',
    data: userData,
    params,
    responseType: options.download ? 'blob' : undefined
  })
}

export const getUserInfo = (userId) => {
  return apiClient({
    url: `/api/v1/users/${userId}`,
    method: 'GET'
  })
}

export const getUserList = (params) => {
  return apiClient({
    url: '/api/v1/users',
    method: 'GET',
    params
  })
}

export const deleteUser = (userId) => {
  return apiClient({
    url: `/api/v1/users/${userId}`,
    method: 'DELETE'
  })
}

export const updateUserInfo = (userId, userData) => {
  return apiClient({
    url: `/api/v1/users/${userId}/update`,
    method: 'PUT',
    data: userData
  })
}

export const updateUserRole = (userId, role) => {
  return apiClient({
    url: `/api/v1/users/${userId}/role`,
    method: 'PUT',
    data: { role }
  })
}

export const adminResetUserInfo = (userId, userData) => {
  return apiClient({
    url: `/api/v1/users/${userId}/admin-reset`,
    method: 'PUT',
    data: userData
  })
}

export const resetUserMfa = (userId) => {
  return apiClient({
    url: `/api/v1/users/${userId}/mfa/reset`,
    method: 'POST',
    data: { confirm: true }
  })
}

export const downloadUserCertificate = (userId) => {
  return apiClient({
    url: '/api/v1/users/certificate/download',
    method: 'GET',
    params: { user_id: userId },
    responseType: 'blob'
  })
}

export const downloadCertificateByDeliveryToken = (token) => {
  return apiClient({
    url: `/api/v1/users/certificate/delivery/${token}`,
    method: 'GET',
    responseType: 'blob'
  })
}
