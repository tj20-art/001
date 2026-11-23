import apiClient from './apiClient'

export const addProduct = (productData) => {
  return apiClient({
    url: '/api/v1/products',
    method: 'POST',
    data: productData
  })
}

export const getProductList = (params, config = {}) => {
  return apiClient({
    ...config,
    url: '/api/v1/products',
    method: 'GET',
    params
  })
}

export const getProductDetail = (productId, config = {}) => {
  return apiClient({
    ...config,
    url: `/api/v1/products/${productId}`,
    method: 'GET'
  })
}

export const updateProduct = (productId, productData) => {
  return apiClient({
    url: `/api/v1/products/${productId}`,
    method: 'PUT',
    data: productData
  })
}

export const deleteProduct = (productId) => {
  return apiClient({
    url: `/api/v1/products/${productId}`,
    method: 'DELETE'
  })
}
