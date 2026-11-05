import apiClient from './apiClient'

export const startPayment = (orderId) => {
  return apiClient({
    url: `/api/v1/pay/start/${orderId}`,
    method: 'POST'
  })
}
