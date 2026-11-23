import apiClient from './apiClient'

export const addCartItem = (data) => {
  return apiClient({
    url: '/api/v1/cart/items',
    method: 'POST',
    data
  })
}

export const getCartItems = (config = {}) => {
  return apiClient({
    ...config,
    url: '/api/v1/cart/items',
    method: 'GET'
  })
}

export const updateCartItem = (cartItemId, data) => {
  return apiClient({
    url: `/api/v1/cart/items/${cartItemId}`,
    method: 'PUT',
    data
  })
}

export const deleteCartItem = (cartItemId) => {
  return apiClient({
    url: `/api/v1/cart/items/${cartItemId}`,
    method: 'DELETE'
  })
}

export const clearCartItems = () => {
  return apiClient({
    url: '/api/v1/cart/items',
    method: 'DELETE'
  })
}

export const bulkSelectCartItems = (data) => {
  return apiClient({
    url: '/api/v1/cart/select',
    method: 'PUT',
    data
  })
}

const managementPath = '/api/v1/cart/management'

export const getCartOwners = (params, config = {}) => apiClient.get(managementPath, { ...config, params })

export const getManagedCart = (userId, config = {}) => apiClient.get(`${managementPath}/${userId}`, config)

export const updateManagedCartQuantity = (userId, itemId, quantity) =>
  apiClient.put(`${managementPath}/${userId}/items/${itemId}`, { quantity })

export const removeManagedCartItem = (userId, itemId) => apiClient.delete(`${managementPath}/${userId}/items/${itemId}`)

export const clearManagedCart = (userId) => apiClient.delete(`${managementPath}/${userId}/items`)
