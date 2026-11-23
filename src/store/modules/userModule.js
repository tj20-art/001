import {
  getUserInfo,
  deleteUser,
  updateUserInfo,
  updateUserRole,
  adminResetUserInfo,
  resetUserMfa
} from '@/services/userService'

const state = {
  userDetail: null
}

const mutations = {
  SET_USER_DETAIL(state, detail) {
    state.userDetail = detail || null
  },
  CLEAR_USER_DETAIL(state) {
    state.userDetail = null
  }
}

const actions = {
  async updateUserInfo(_, { userId, userData }) {
    return updateUserInfo(userId, userData)
  },
  async getUserInfo({ commit }, userId) {
    const response = await getUserInfo(userId)
    commit('SET_USER_DETAIL', response.data && response.data.user_info)
    return response
  },
  async deleteUser(_, userId) {
    return deleteUser(userId)
  },
  async updateUserRole(_, { userId, role }) {
    return updateUserRole(userId, role)
  },
  async adminResetUserInfo(_, { userId, userData }) {
    return adminResetUserInfo(userId, userData)
  },
  async resetUserMfa(_, userId) {
    return resetUserMfa(userId)
  }
}

export default {
  namespaced: true,
  state,
  mutations,
  actions
}
