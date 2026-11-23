<template>
  <div class="page-shell">
    <CommonHeader />
    <main class="page-main cart-main">
      <header class="cart-heading">
        <div>
          <p class="muted-text">{{ cartItems.length }} 款商品</p>
          <h1>我的购物车</h1>
        </div>
        <RouterLink to="/home" class="continue-link">继续购物</RouterLink>
      </header>

      <AppLoading v-if="loading" />
      <ListError v-else-if="loadError" :message="loadError" @retry="loadCart" />
      <section v-else-if="cartItems.length" class="section-card">
        <div class="cart-toolbar">
          <el-checkbox :model-value="allSelected" :disabled="busy" @change="handleToggleAll">全选</el-checkbox>
          <el-button text type="danger" :disabled="busy" @click="handleClearCart">清空购物车</el-button>
        </div>
        <ul class="cart-items">
          <li v-for="item in cartItems" :key="item.id" class="cart-row">
            <el-checkbox
              :model-value="item.selected"
              :disabled="busy"
              :aria-label="'选择 ' + item.product_name"
              @change="handleToggleItem(item, $event)"
            />
            <div class="cart-product">
              <img v-if="coverOf(item)" :src="coverOf(item)" :alt="item.product_name" loading="lazy" />
              <div v-else class="cart-placeholder" aria-hidden="true">
                <el-icon><Box /></el-icon>
              </div>
              <div>
                <strong>{{ item.product_name }}</strong>
                <span>{{ money(item.price) }} · 库存 {{ item.stock }}</span>
              </div>
            </div>
            <div class="cart-controls">
              <el-input-number
                :model-value="item.quantity"
                :min="1"
                :max="Math.max(1, Number(item.stock || 1))"
                :disabled="busy"
                :aria-label="item.product_name + ' 数量'"
                size="small"
                @change="handleQuantityChange(item, $event)"
              />
              <strong>{{ money(item.subtotal) }}</strong>
              <el-button text type="danger" :disabled="busy" @click="handleRemoveItem(item.id)">删除</el-button>
            </div>
          </li>
        </ul>
      </section>
      <el-empty v-else description="购物车还是空的">
        <el-button type="primary" @click="$router.push('/home')">去逛逛</el-button>
      </el-empty>

      <footer v-if="!loading && !loadError && (cartItems.length || checkoutKey)" class="checkout-bar section-card">
        <div>
          <span>已选 {{ selectedCount }} 款</span>
          <strong>{{ money(selectedTotal) }}</strong>
        </div>
        <el-button
          type="primary"
          :loading="checkingOut"
          :disabled="busy || (!selectedCount && !checkoutKey)"
          @click="handleCreateOrder"
        >
          {{ selectedCount ? '提交订单' : '确认上次下单' }}
        </el-button>
      </footer>
    </main>
  </div>
</template>

<script>
import { mapActions, mapGetters } from 'vuex'
import CommonHeader from '@/components/CommonHeader.vue'
import AppLoading from '@/components/AppLoading.vue'
import ListError from '@/components/ListError.vue'
import { coverOf, money } from '@/utils/productDisplay'

export default {
  name: 'CartPage',
  components: { CommonHeader, AppLoading, ListError },
  data() {
    return { loadError: '', updating: false, checkingOut: false, checkoutKey: '' }
  },
  computed: {
    ...mapGetters('cartModule', ['cartItems', 'selectedTotal', 'selectedCount', 'isCartLoading']),
    ...mapGetters('authModule', ['userId']),
    loading() {
      return this.isCartLoading
    },
    busy() {
      return this.updating || this.checkingOut
    },
    allSelected() {
      return this.cartItems.length > 0 && this.cartItems.every((item) => item.selected)
    },
    checkoutStorageKey() {
      return 'mall.checkout.' + this.userId
    }
  },
  mounted() {
    this.checkoutKey = sessionStorage.getItem(this.checkoutStorageKey) || ''
    this.loadCart()
  },
  methods: {
    ...mapActions('cartModule', ['fetchCart', 'updateCartItem', 'deleteCartItem', 'clearCart', 'bulkSelectCart']),
    ...mapActions('orderModule', ['createOrder']),
    coverOf,
    money,
    async loadCart() {
      this.loadError = ''
      try {
        await this.fetchCart({ silentError: true })
      } catch (error) {
        this.loadError = error.response?.data?.message || '购物车加载失败，请重试。'
      }
    },
    rememberCheckout(key, storageKey = this.checkoutStorageKey) {
      if (key) sessionStorage.setItem(storageKey, key)
      else sessionStorage.removeItem(storageKey)
      if (storageKey === this.checkoutStorageKey) this.checkoutKey = key
    },
    async updateCart(operation) {
      if (this.busy) return
      this.updating = true
      const storageKey = this.checkoutStorageKey
      try {
        await operation()
        this.rememberCheckout('', storageKey)
      } catch {
        // The API client reports cart update failures.
      } finally {
        this.updating = false
      }
    },
    handleQuantityChange(item, value) {
      if (!Number.isInteger(value) || value === item.quantity) return
      return this.updateCart(() => this.updateCartItem({ cartItemId: item.id, payload: { quantity: value } }))
    },
    handleToggleItem(item, value) {
      return this.updateCart(() => this.updateCartItem({ cartItemId: item.id, payload: { selected: value } }))
    },
    handleToggleAll(selected) {
      return this.updateCart(() => this.bulkSelectCart({ selected }))
    },
    handleRemoveItem(itemId) {
      return this.updateCart(() => this.deleteCartItem(itemId))
    },
    async handleClearCart() {
      try {
        await this.$confirm('确定要清空购物车吗？', '清空购物车', {
          confirmButtonText: '清空',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.updateCart(() => this.clearCart())
      } catch {
        // The user dismissed the confirmation.
      }
    },
    async handleCreateOrder() {
      if (this.busy || (!this.selectedCount && !this.checkoutKey)) return
      this.checkingOut = true
      const storageKey = this.checkoutStorageKey
      try {
        const checkoutKey = this.checkoutKey || crypto.randomUUID()
        this.rememberCheckout(checkoutKey, storageKey)
        const response = await this.createOrder({ checkout_key: checkoutKey })
        this.rememberCheckout('', storageKey)
        this.$message.success(response.message || '订单创建成功')
        this.fetchCart({ silentError: true }).catch(() => {})
        const orderId = response.data?.order?.id
        await this.$router.push({ path: '/orders', query: orderId ? { order: orderId } : {} })
      } catch (error) {
        if (error.response?.status === 400) this.rememberCheckout('', storageKey)
      } finally {
        this.checkingOut = false
      }
    }
  }
}
</script>

<style scoped>
.cart-main {
  max-width: 1060px;
  padding-bottom: 116px;
}
.cart-heading,
.cart-toolbar,
.checkout-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.cart-heading {
  margin-bottom: 20px;
}
.cart-heading p {
  margin: 0 0 4px;
  font-size: 14px;
}
.cart-heading h1 {
  margin: 0;
  font-size: clamp(26px, 4vw, 36px);
}
.continue-link {
  color: var(--mall-accent);
  font-weight: 600;
}
.cart-toolbar {
  padding: 12px 20px;
  border-bottom: 1px solid var(--mall-border);
}
.cart-items {
  padding: 0;
  margin: 0;
  list-style: none;
}
.cart-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
}
.cart-row + .cart-row {
  border-top: 1px solid var(--mall-border);
}
.cart-product,
.cart-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.cart-product img,
.cart-placeholder {
  flex: none;
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 8px;
}
.cart-placeholder {
  display: grid;
  place-items: center;
  background: var(--mall-accent-soft);
  color: var(--mall-accent);
}
.cart-product strong,
.cart-product span {
  display: block;
  overflow-wrap: anywhere;
}
.cart-product span,
.checkout-bar span {
  color: var(--mall-muted);
  font-size: 13px;
}
.checkout-bar {
  position: sticky;
  bottom: 12px;
  padding: 12px 20px;
  margin-top: 16px;
  z-index: 5;
}
.checkout-bar strong {
  margin-left: 12px;
  color: var(--mall-accent);
  font-size: 22px;
}
.checkout-bar .el-button {
  min-height: 40px;
}
@media (max-width: 640px) {
  .cart-toolbar,
  .cart-row {
    padding-inline: 12px;
  }
  .cart-row {
    grid-template-columns: auto minmax(0, 1fr);
    gap: 8px;
  }
  .cart-controls {
    grid-column: 2;
    flex-wrap: wrap;
    gap: 6px;
  }
  .cart-controls :deep(.el-input-number) {
    width: 104px;
  }
  .cart-product img,
  .cart-placeholder {
    width: 54px;
    height: 54px;
  }
  .checkout-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    padding: 12px 16px max(12px, env(safe-area-inset-bottom));
    border-radius: 0;
  }
  .checkout-bar strong {
    display: block;
    margin-left: 0;
  }
}
</style>
