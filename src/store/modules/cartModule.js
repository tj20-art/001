import {
  addCartItem,
  getCartItems,
  updateCartItem,
  deleteCartItem,
  clearCartItems,
  bulkSelectCartItems
} from '@/services/cartService'

const createDefaultCart = () => ({
  items: [],
  selected_total_cents: 0,
  selected_total: 0
})

const state = {
  cart: createDefaultCart(),
  loading: false
}

const mutations = {
  SET_CART(state, payload) {
    state.cart = {
      ...createDefaultCart(),
      ...(payload || {})
    }
  },
  SET_LOADING(state, loading) {
    state.loading = !!loading
  },
  CLEAR_CART(state) {
    state.cart = createDefaultCart()
  }
}

const actions = {
  async fetchCart({ commit }) {
    commit('SET_LOADING', true)
    try {
      const response = await getCartItems()
      commit('SET_CART', response.data)
      return response
    } finally {
      commit('SET_LOADING', false)
    }
  },
  async addToCart({ commit }, payload) {
    const response = await addCartItem(payload)
    commit('SET_CART', response.data)
    return response
  },
  async updateCartItem({ commit }, { cartItemId, payload }) {
    const response = await updateCartItem(cartItemId, payload)
    commit('SET_CART', response.data)
    return response
  },
  async deleteCartItem({ commit }, cartItemId) {
    const response = await deleteCartItem(cartItemId)
    commit('SET_CART', response.data)
    return response
  },
  async clearCart({ commit }) {
    const response = await clearCartItems()
    commit('SET_CART', response.data)
    return response
  },
  async bulkSelectCart({ commit }, payload) {
    const response = await bulkSelectCartItems(payload)
    commit('SET_CART', response.data)
    return response
  }
}

const getters = {
  cartItems: (state) => state.cart.items || [],
  cartCount: (state, getters) => getters.cartItems.length,
  selectedTotal: (state) => Number(state.cart.selected_total || 0),
  selectedTotalCents: (state) => Number(state.cart.selected_total_cents || 0),
  selectedCount: (state, getters) => getters.cartItems.filter((item) => item.selected).length,
  isCartLoading: (state) => state.loading
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
