<template>
  <header class="common-header">
    <div class="topbar">
      <RouterLink class="brand" to="/home" aria-label="FreeSpace Mall 商城首页">
        <span class="brand-mark" aria-hidden="true">FS</span>
        <strong>FreeSpace Mall</strong>
      </RouterLink>
      <nav class="nav-center" aria-label="商城导航">
        <RouterLink to="/home" class="nav-link">商城首页</RouterLink>
        <template v-if="isAuthenticated">
          <RouterLink v-if="canManageProducts" to="/my-products" class="nav-link">商品管理</RouterLink>
          <RouterLink v-if="isAdmin" to="/cart-management" class="nav-link">购物车管理</RouterLink>
          <RouterLink v-if="canShop" to="/orders" class="nav-link">我的订单</RouterLink>
          <RouterLink v-if="isAdmin" to="/user-list" class="nav-link">用户管理</RouterLink>
          <RouterLink v-if="isAdmin || isAuditor" to="/security-center" class="nav-link">安全审计</RouterLink>
        </template>
      </nav>
      <div v-if="!isAuthenticated" class="actions">
        <RouterLink to="/user-login" class="account-link">登录</RouterLink>
        <RouterLink to="/user-register" class="register-link">注册</RouterLink>
      </div>
      <div v-else class="actions">
        <RouterLink v-if="canShop" to="/cart" class="cart-link" aria-label="购物车">
          <el-badge :value="cartCount" :hidden="!cartCount" :max="99">
            <el-icon aria-hidden="true"><ShoppingCart /></el-icon>
          </el-badge>
        </RouterLink>
        <RouterLink :to="'/profile/' + userId" :aria-label="'个人中心，' + username" class="account-link">
          <span class="account-name">{{ username }}</span>
          <span class="account-compact">我的</span>
        </RouterLink>
        <el-tag class="role-tag" size="small" :type="roleTagType">{{ roleLabel }}</el-tag>
        <button class="sign-out" type="button" @click="handleLogout">退出</button>
      </div>
    </div>
  </header>
</template>

<script>
import { mapState, mapGetters, mapMutations } from 'vuex'

export default {
  name: 'CommonHeader',
  computed: {
    ...mapState('authModule', ['isAuthenticated', 'user']),
    ...mapGetters('authModule', ['isAdmin', 'isAuditor', 'canManageProducts', 'canShop', 'userId']),
    ...mapGetters('cartModule', ['cartCount']),
    username() {
      return this.user ? this.user.username : '游客'
    },
    roleLabel() {
      const labels = { user: '会员', merchant: '商户', admin: '管理员', auditor: '审计员' }
      return labels[this.user?.role] || '访客'
    },
    roleTagType() {
      return { user: 'success', merchant: 'primary', admin: 'warning', auditor: 'info' }[this.user?.role] || 'info'
    }
  },
  methods: {
    ...mapMutations('authModule', ['LOGOUT']),
    handleLogout() {
      this.$confirm('确定要退出当前账号吗？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(() => {
          this.LOGOUT()
          this.$message.success('已安全退出')
          return this.$router.replace('/user-login')
        })
        .catch(() => {})
    }
  }
}
</script>

<style scoped>
.common-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: #fffdf9;
  border-bottom: 1px solid var(--mall-border);
}
.topbar {
  max-width: 1280px;
  min-height: 64px;
  margin: auto;
  padding: 8px 24px;
  display: flex;
  align-items: center;
  gap: 20px;
}
.brand,
.nav-center,
.actions {
  display: flex;
  align-items: center;
}
.brand {
  flex: none;
  gap: 8px;
  font-size: 16px;
  letter-spacing: -0.025em;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: var(--mall-accent);
  color: white;
  font-size: 13px;
}
.nav-center {
  flex: 1;
  justify-content: center;
  flex-wrap: wrap;
  gap: 2px 10px;
}
.nav-link {
  min-height: 36px;
  padding: 8px 6px;
  color: var(--mall-muted);
  font-size: 14px;
  border-bottom: 2px solid transparent;
}
.nav-link:hover,
.nav-link.router-link-active {
  color: var(--mall-accent);
}
.nav-link.router-link-active {
  border-color: var(--mall-accent);
}
.actions {
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.account-link,
.sign-out,
.register-link,
.cart-link {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 5px;
  font-size: 14px;
  white-space: nowrap;
}
.account-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.account-compact {
  display: none;
}
.sign-out {
  border: 0;
  background: transparent;
  color: var(--mall-muted);
  cursor: pointer;
}
.register-link {
  background: var(--mall-accent);
  border-radius: 8px;
  color: white;
  padding-inline: 12px;
}
.cart-link {
  width: 34px;
  font-size: 21px;
}
.cart-link :deep(.el-badge) {
  display: inline-flex;
}
.role-tag {
  flex: none;
}
@media (max-width: 820px) {
  .topbar {
    flex-wrap: wrap;
    gap: 0 12px;
    padding-inline: 16px;
  }
  .nav-center {
    justify-content: flex-start;
    order: 3;
    flex: 1 0 100%;
  }
}
@media (max-width: 510px) {
  .topbar {
    column-gap: 4px;
  }
  .brand {
    font-size: 14px;
    gap: 6px;
  }
  .brand-mark {
    width: 28px;
    height: 28px;
  }
  .actions {
    gap: 2px;
  }
  .account-name,
  .role-tag {
    display: none;
  }
  .account-compact {
    display: inline;
  }
  .nav-link {
    font-size: 13px;
  }
}
@media (max-width: 350px) {
  .cart-link {
    width: 26px;
  }
  .sign-out,
  .account-link {
    padding-inline: 3px;
  }
}
</style>
