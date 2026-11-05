import {
  getUserInfo,
  getUserList,
  deleteUser,
  updateUserInfo,
  updateUserRole,
  adminResetUserInfo,
  resetUserMfa
} from '@/services/userService'

const state = {
  userDetail: null,
  userList: []
}

const mutations = {
  SET_USER_DETAIL(state, detail) {
    state.userDetail = detail || null
  },
  SET_USER_LIST(state, list) {
    state.userList = list || []
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
  async getUserList({ commit }, params) {
    const response = await getUserList(params)
    commit('SET_USER_LIST', (response.data && response.data.user_list) || [])
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

const getters = {
  userListCount: (state) => state.userList.length
}

export default {
  namespaced: true,
  state,
  mutations,
  actions,
  getters
}
