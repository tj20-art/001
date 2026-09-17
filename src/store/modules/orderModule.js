import { createOrder, getOrderList, getOrderDetail, cancelOrder } from '@/services/orderService'
import { startPayment } from '@/services/payService'

const state = {
  orderList: [],
  currentOrder: null,
  loading: false
}

const mutations = {
  SET_ORDER_LIST(state, list) {
    state.orderList = list || []
  },
  SET_CURRENT_ORDER(state, order) {
    state.currentOrder = order || null
  },
  SET_LOADING(state, loading) {
    state.loading = !!loading
  }
}

const actions = {
  async fetchOrderList({ commit }, params = {}) {
    commit('SET_LOADING', true)
    try {
      const response = await getOrderList(params)
      commit('SET_ORDER_LIST', (response.data && response.data.order_list) || [])
      return response
    } finally {
      commit('SET_LOADING', false)
    }
  },
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

const getters = {
  pendingOrderCount: (state) => state.orderList.filter((item) => item.status === 'pending').length,
  isOrderLoading: (state) => state.loading
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
