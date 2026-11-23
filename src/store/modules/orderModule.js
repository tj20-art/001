import { createOrder, getOrderDetail, cancelOrder } from '@/services/orderService'
import { startPayment } from '@/services/payService'

const state = {
  currentOrder: null
}

const mutations = {
  SET_CURRENT_ORDER(state, order) {
    state.currentOrder = order || null
  }
}

const actions = {
  async fetchOrderDetail({ commit }, orderId) {
    const response = await getOrderDetail(orderId)
    commit('SET_CURRENT_ORDER', response.data && response.data.order)
    return response
  },
  async createOrder({ commit }, payload) {
    const response = await createOrder(payload)
    commit('SET_CURRENT_ORDER', response.data && response.data.order)
    return response
  },
  async cancelOrder({ commit }, orderId) {
    const response = await cancelOrder(orderId)
    commit('SET_CURRENT_ORDER', response.data && response.data.order)
    return response
  },
  async startPayment(_, orderId) {
    return startPayment(orderId)
  }
}

export default {
  namespaced: true,
  state,
  mutations,
  actions
}
