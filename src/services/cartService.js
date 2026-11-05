import apiClient from './apiClient'

export const addCartItem = (data) => {
  return apiClient({
    url: '/api/v1/cart/items',
    method: 'POST',
    data
  })
}

export const getCartItems = () => {
  return apiClient({
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
