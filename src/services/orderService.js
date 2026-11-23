import apiClient from './apiClient'

export const createOrder = (data) => {
  return apiClient({
    url: '/api/v1/orders',
    method: 'POST',
    data
  })
}

export const getOrderList = (params, config = {}) => {
  return apiClient({
    ...config,
    url: '/api/v1/orders',
    method: 'GET',
    params
  })
}

export const getOrderStatus = (orderNo, config = {}) => {
  return apiClient({
    ...config,
    url: '/api/v1/orders/status',
    params: { order_no: orderNo }
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
