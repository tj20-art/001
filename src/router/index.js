import Vue from 'vue'
import Router from 'vue-router'
import store from '@/store'

const Login = () => import('@/pages/UserLogin')
const Register = () => import('@/pages/UserRegister')
const Profile = () => import('@/pages/UserProfile')
const UserList = () => import('@/pages/UserList')
const NotFound = () => import('@/pages/PageNotFound')
const ProductList = () => import('@/pages/ProductList')
const ProductHome = () => import('@/pages/ProductHome')
const CartPage = () => import('@/pages/CartPage')
const OrderList = () => import('@/pages/OrderList')
const PayResult = () => import('@/pages/PayResult')
const SecurityCenter = () => import('@/pages/SecurityCenter')

Vue.use(Router)

const router = new Router({
  mode: 'hash',
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', component: ProductHome },
    { path: '/user-login', component: Login, meta: { noAuth: true } },
    { path: '/user-register', component: Register, meta: { noAuth: true } },
    { path: '/profile/:user_id', component: Profile, meta: { requiresAuth: true } },
    { path: '/my-products', component: ProductList, meta: { requiresAuth: true, allowedRoles: ['merchant', 'admin'] } },
    { path: '/product-list', redirect: '/my-products' },
    { path: '/cart', component: CartPage, meta: { requiresAuth: true, allowedRoles: ['user'] } },
    { path: '/orders', component: OrderList, meta: { requiresAuth: true, allowedRoles: ['user'] } },

    // 支付结果页允许银行系统跳回，即使登录态丢失也先展示结果
    { path: '/pay-result', component: PayResult, meta: { allowAnonymous: true } },

    { path: '/user-list', component: UserList, meta: { requiresAuth: true, requiresAdmin: true } },
    {
      path: '/security-center',
      component: SecurityCenter,
      meta: { requiresAuth: true, allowedRoles: ['admin', 'auditor'] }
    },
    { path: '*', component: NotFound }
  ]
})

router.beforeEach((to, from, next) => {
  const isAuthenticated = store.state.authModule.isAuthenticated
  const user = store.state.authModule.user

  const userRole = user ? user.role : ''
  const userId = user ? String(user.id || user.user_id || '') : ''

  if (to.meta.requiresAuth && !isAuthenticated) {
    next('/user-login')
    return
  }

  if (to.path.startsWith('/profile/') && isAuthenticated && userRole !== 'admin') {
    const routeUserId = String(to.params.user_id || '')

    if (routeUserId && userId && routeUserId !== userId) {
      next(`/profile/${userId}`)
      return
    }

    if (!userId) {
      next('/user-login')
      return
    }
  }

  if (to.meta.requiresAdmin && userRole !== 'admin') {
    next(userId ? `/profile/${userId}` : '/user-login')
    return
  }

  if (to.meta.allowedRoles && !to.meta.allowedRoles.includes(userRole)) {
    next(userId ? `/profile/${userId}` : '/user-login')
    return
  }

  if (to.meta.noAuth && isAuthenticated) {
    next('/home')
    return
  }

  next()
})

export default router
