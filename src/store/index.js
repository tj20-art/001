import Vue from 'vue'
import Vuex from 'vuex'
import createPersistedState from 'vuex-persistedstate'
import authModule from './modules/authModule'
import userModule from './modules/userModule'
import productModule from './modules/productModule'
import cartModule from './modules/cartModule'
import orderModule from './modules/orderModule'

Vue.use(Vuex)

export default new Vuex.Store({
  modules: {
    authModule,
    userModule,
    productModule,
    cartModule,
    orderModule
  },
  plugins: [
    createPersistedState({
      storage: window.sessionStorage,
      paths: ['authModule.user', 'authModule.accessToken', 'authModule.refreshToken']
    })
  ]
})
