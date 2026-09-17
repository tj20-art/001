import { getProductList, addProduct, updateProduct, deleteProduct, getProductDetail } from '@/services/productService'

const state = {
  productList: [],
  currentProduct: null,
  loading: false
}

const mutations = {
  SET_PRODUCT_LIST(state, list) {
    state.productList = list || []
  },
  SET_CURRENT_PRODUCT(state, product) {
    state.currentProduct = product || null
  },
  SET_LOADING(state, isLoading) {
    state.loading = isLoading
  },
  CLEAR_CURRENT_PRODUCT(state) {
    state.currentProduct = null
  }
}

const actions = {
  async fetchProductList({ commit }, params = {}) {
    commit('SET_LOADING', true)
    try {
      const response = await getProductList(params)
      commit('SET_PRODUCT_LIST', (response.data && response.data.product_list) || [])
      return response
    } finally {
      commit('SET_LOADING', false)
    }
  },

  async addProduct(_, productData) {
    return addProduct(productData)
  },

  async updateProduct(_, { productId, productData }) {
    return updateProduct(productId, productData)
  },

  async deleteProduct(_, productId) {
    return deleteProduct(productId)
  },

  async fetchProductDetail({ commit }, productId) {
    commit('SET_LOADING', true)
    try {
      const response = await getProductDetail(productId)
      commit('SET_CURRENT_PRODUCT', response.data && response.data.product_info)
      return response
    } finally {
      commit('SET_LOADING', false)
    }
  }
}

const getters = {
  productListCount: (state) => state.productList.length,
  isProductLoading: (state) => state.loading
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
