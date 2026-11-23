import { createRouter, createWebHashHistory } from 'vue-router'
import store from '@/store'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', component: () => import('@/pages/ProductHome.vue') },
    { path: '/user-login', component: () => import('@/pages/UserLogin.vue'), meta: { noAuth: true } },
    { path: '/user-register', component: () => import('@/pages/UserRegister.vue'), meta: { noAuth: true } },
    { path: '/profile/:user_id', component: () => import('@/pages/UserProfile.vue'), meta: { requiresAuth: true } },
    {
      path: '/my-products',
      component: () => import('@/pages/ProductList.vue'),
      meta: { requiresAuth: true, allowedRoles: ['merchant', 'admin'] }
    },
    { path: '/product-list', redirect: '/my-products' },
    {
      path: '/cart',
      component: () => import('@/pages/CartPage.vue'),
      meta: { requiresAuth: true, allowedRoles: ['user'] }
    },
    {
      path: '/cart-management',
      component: () => import('@/pages/CartManagement.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/orders',
      component: () => import('@/pages/OrderList.vue'),
      meta: { requiresAuth: true, allowedRoles: ['user'] }
    },
    {
      path: '/pay-result',
      component: () => import('@/pages/PayResult.vue'),
      meta: { restoreAuth: true, allowedRoles: ['user'] }
    },
    {
      path: '/user-list',
      component: () => import('@/pages/UserList.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/security-center',
      component: () => import('@/pages/SecurityCenter.vue'),
      meta: { requiresAuth: true, allowedRoles: ['admin', 'auditor'] }
    },
    { path: '/:pathMatch(.*)*', component: () => import('@/pages/PageNotFound.vue') }
  ]
})

let authReady
router.beforeEach(async (to) => {
  authReady ??= store.dispatch('authModule/initAuthState')
  if (to.meta.requiresAuth || to.meta.noAuth || to.meta.restoreAuth) await authReady

  const { isAuthenticated, user } = store.state.authModule
  const userRole = user?.role
  const userId = String(user?.id || user?.user_id || '')
  const profilePath = userId ? '/profile/' + userId : '/user-login'

  if (to.meta.requiresAuth && !isAuthenticated) {
    return { path: '/user-login', query: { redirect: to.fullPath }, replace: true }
  }

  if (to.path.startsWith('/profile/') && userRole !== 'admin' && to.params.user_id !== userId) {
    return profilePath
  }

  if (to.meta.requiresAdmin && userRole !== 'admin') return profilePath
  if (isAuthenticated && to.meta.allowedRoles && !to.meta.allowedRoles.includes(userRole)) return profilePath
  if (to.meta.noAuth && isAuthenticated) return '/home'
})

export default router
