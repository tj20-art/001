import { createStore } from 'vuex'
import authModule from './modules/authModule'
import userModule from './modules/userModule'
import cartModule from './modules/cartModule'
import orderModule from './modules/orderModule'

export default createStore({
  modules: {
    authModule,
    userModule,
    cartModule,
    orderModule
  },
  plugins: [
    (store) =>
      store.subscribe(({ type }) => {
        if (type !== 'authModule/LOGOUT') return
        store.commit('cartModule/CLEAR_CART')
        store.commit('userModule/CLEAR_USER_DETAIL')
        store.commit('orderModule/SET_CURRENT_ORDER', null)
      })
  ]
})
