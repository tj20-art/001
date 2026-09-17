<template>
  <div class="page-shell cart-page">
    <common-header />

    <main class="cart-main page-main">
      <section class="page-head section-card">
        <div>
          <h1>我的购物车</h1>
          <p>所有购物车接口都已对齐后端，只会操作当前登录用户自己的数据。</p>
        </div>
        <div class="head-actions">
          <el-button plain @click="$router.push('/home')">继续购物</el-button>
          <el-button type="danger" plain :disabled="!cartItems.length" @click="handleClearCart">清空购物车</el-button>
        </div>
      </section>

      <section class="summary-grid">
        <div class="summary-card section-card">
          <span>购物车商品</span>
          <strong>{{ cartItems.length }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>已勾选数量</span>
          <strong>{{ selectedCount }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>已勾选总额</span>
          <strong>{{ formatPrice(selectedTotal) }}</strong>
        </div>
      </section>

      <app-loading v-if="loading" />

      <section v-else class="cart-card section-card">
        <div class="toolbar-row" v-if="cartItems.length">
          <el-checkbox :value="allSelected" @change="handleToggleAll">全选 / 取消全选</el-checkbox>
          <div class="toolbar-actions">
            <el-button type="primary" :disabled="!selectedCount" @click="handleCreateOrder">生成订单</el-button>
          </div>
        </div>

        <el-table v-if="cartItems.length" :data="cartItems" border stripe>
          <el-table-column width="70" align="center">
            <template slot-scope="scope">
              <el-checkbox :value="scope.row.selected" @change="(value) => handleToggleItem(scope.row, value)" />
            </template>
          </el-table-column>
          <el-table-column label="商品" min-width="280">
            <template slot-scope="scope">
              <div class="product-cell">
                <img
                  v-if="getCoverImage(scope.row)"
                  :src="getCoverImage(scope.row)"
                  class="product-thumb"
                  alt="thumb"
                />
                <div class="product-info">
                  <strong>{{ scope.row.product_name }}</strong>
                  <span>商品ID：{{ scope.row.product_id }}</span>
                  <span>卖家ID：{{ scope.row.seller_id }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="单价" width="120" align="center">
            <template slot-scope="scope">{{ formatPrice(scope.row.price) }}</template>
          </el-table-column>
          <el-table-column label="库存" prop="stock" width="100" align="center" />
          <el-table-column label="数量" width="180" align="center">
            <template slot-scope="scope">
              <el-input-number
                :value="scope.row.quantity"
                :min="1"
                :max="Math.max(1, Number(scope.row.stock || 1))"
                size="small"
                @change="(value) => handleQuantityChange(scope.row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="小计" width="130" align="center">
            <template slot-scope="scope">{{ formatPrice(scope.row.subtotal) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template slot-scope="scope">
              <el-button type="text" style="color: #ef4444" @click="handleRemoveItem(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty-wrap">
          <el-empty description="购物车还是空的，先去首页挑选商品吧">
            <el-button type="primary" @click="$router.push('/home')">去逛逛</el-button>
          </el-empty>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapGetters } from 'vuex'

export default {
  name: 'CartPage',
  components: { CommonHeader, AppLoading },
  computed: {
    ...mapGetters('cartModule', ['cartItems', 'selectedTotal', 'selectedCount', 'isCartLoading']),
    loading() {
      return this.isCartLoading
    },
    allSelected() {
      return !!this.cartItems.length && this.cartItems.every((item) => item.selected)
    }
  },
  mounted() {
    this.fetchCart()
  },
  methods: {
    ...mapActions('cartModule', ['fetchCart', 'updateCartItem', 'deleteCartItem', 'clearCart', 'bulkSelectCart']),
    ...mapActions('orderModule', ['createOrder']),
    getCoverImage(item) {
      return (item.image_urls && item.image_urls[0]) || item.image_url || ''
    },
    formatPrice(value) {
      return `¥${Number(value || 0).toFixed(2)}`
    },
    async handleQuantityChange(item, value) {
      await this.updateCartItem({
        cartItemId: item.id,
        payload: { quantity: value }
      })
    },
    async handleToggleItem(item, value) {
      await this.updateCartItem({
        cartItemId: item.id,
        payload: { selected: value }
      })
    },
    async handleToggleAll(value) {
      await this.bulkSelectCart({ selected: value })
    },
    async handleRemoveItem(cartItemId) {
      await this.deleteCartItem(cartItemId)
      this.$message.success('购物车条目已删除')
    },
    async handleClearCart() {
      try {
        await this.$confirm('确定要清空购物车吗？', '清空购物车', {
          confirmButtonText: '清空',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.clearCart()
        this.$message.success('购物车已清空')
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          // handled by interceptor
        }
      }
    },
    async handleCreateOrder() {
      const response = await this.createOrder()
      await this.fetchCart()
      this.$message.success(response.message || '订单创建成功')
      this.$router.push('/orders')
    }
  }
}
</script>

<style scoped lang="scss">
.page-head,
.cart-card {
  padding: 24px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.page-head h1 {
  margin: 0 0 10px;
  font-size: 30px;
}

.page-head p {
  margin: 0;
  color: #6b7280;
}

.head-actions {
  display: flex;
  gap: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 18px;
}

.summary-card {
  padding: 22px;
}

.summary-card span {
  display: block;
  color: #6b7280;
  margin-bottom: 8px;
}

.summary-card strong {
  font-size: 28px;
}

.toolbar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.product-cell {
  display: flex;
  align-items: center;
  gap: 14px;
}

.product-thumb {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 14px;
}

.product-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.product-info strong {
  color: #111827;
}

.product-info span {
  color: #6b7280;
  font-size: 12px;
}

@media screen and (max-width: 960px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .page-head,
  .toolbar-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
