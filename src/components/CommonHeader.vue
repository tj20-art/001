<template>
  <header class="common-header">
    <div class="topbar">
      <div class="brand" @click="$router.push('/home')">
        <div class="brand-mark">FS</div>
        <div class="brand-text">
          <strong>FreeSpace Mall</strong>
          <span>可信身份 · 安全交易</span>
        </div>
      </div>

      <div class="nav-center">
        <router-link to="/home" class="nav-link">商城首页</router-link>
        <router-link v-if="isAuthenticated" :to="`/profile/${userId}`" class="nav-link">个人中心</router-link>
        <router-link v-if="canManageProducts" to="/my-products" class="nav-link">商品管理</router-link>
        <router-link v-if="canShop" to="/orders" class="nav-link">我的订单</router-link>
        <router-link v-if="isAdmin" to="/user-list" class="nav-link">用户管理</router-link>
        <router-link v-if="isAdmin || isAuditor" to="/security-center" class="nav-link">安全审计</router-link>
      </div>

      <div class="actions" v-if="!isAuthenticated">
        <router-link to="/user-login" class="ghost-link">登录</router-link>
        <el-button type="primary" size="small" round @click="$router.push('/user-register')">立即注册</el-button>
      </div>

      <div class="actions" v-else>
        <router-link v-if="canShop" to="/cart" class="cart-link">
          <el-badge :value="cartCount" :hidden="!cartCount" :max="99">
            <i class="el-icon-shopping-cart-2"></i>
          </el-badge>
        </router-link>
        <el-tag size="mini" :type="roleTagType">{{ roleLabel }}</el-tag>
        <div class="welcome">你好，{{ username }}</div>
        <el-button type="text" @click="handleLogout">退出</el-button>
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
      return { user: 'success', merchant: '', admin: 'warning', auditor: 'info' }[this.user?.role] || 'info'
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
          this.$router.push('/user-login')
        })
        .catch(() => {})
    }
  }
}
</script>

<style scoped lang="scss">
.common-header {
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(14px);
  background: rgba(12, 23, 36, 0.88);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.topbar {
  max-width: 1280px;
  margin: 0 auto;
  min-height: 72px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #409eff, #7c4dff);
  color: #fff;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 18px rgba(64, 158, 255, 0.32);
}

.brand-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;

  strong {
    color: #fff;
    font-size: 17px;
    line-height: 1.2;
  }

  span {
    color: rgba(255, 255, 255, 0.72);
    font-size: 12px;
    margin-top: 2px;
  }
}

.nav-center {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: 1;
  justify-content: center;
  flex-wrap: wrap;
}

.nav-link,
.ghost-link,
.cart-link {
  color: rgba(255, 255, 255, 0.86);
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s ease;
}

.nav-link:hover,
.ghost-link:hover,
.cart-link:hover {
  color: #ffffff;
}

.cart-link {
  font-size: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.welcome {
  color: #fff;
  font-size: 14px;
  max-width: 180px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media screen and (max-width: 960px) {
  .topbar {
    flex-wrap: wrap;
    padding: 14px 16px;
  }

  .nav-center {
    order: 3;
    width: 100%;
    justify-content: flex-start;
    gap: 14px;
    padding-bottom: 6px;
  }
}
</style>
