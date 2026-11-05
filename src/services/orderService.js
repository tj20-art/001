import apiClient from './apiClient'

export const createOrder = () => {
  return apiClient({
    url: '/api/v1/orders',
    method: 'POST'
  })
}

export const getOrderList = (params) => {
  return apiClient({
    url: '/api/v1/orders',
    method: 'GET',
    params
  })
}

export const getOrderDetail = (orderId) => {
  return apiClient({
    url: `/api/v1/orders/${orderId}`,
    method: 'GET'
  })
}

export const cancelOrder = (orderId) => {
  return apiClient({
    url: `/api/v1/orders/${orderId}/cancel`,
    method: 'POST'
  })
}
