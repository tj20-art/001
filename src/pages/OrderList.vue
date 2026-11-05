<template>
  <div class="page-shell order-page">
    <common-header />

    <main class="order-main page-main">
      <section class="page-head section-card">
        <div>
          <h1>我的订单</h1>
          <p>订单列表、详情和取消订单都已经对齐后端接口，并且只读取当前用户自己的订单数据。</p>
        </div>
        <div class="head-actions">
          <el-select
            v-model="statusFilter"
            clearable
            placeholder="订单状态"
            @change="fetchOrders"
            class="status-select"
          >
            <el-option label="全部订单" value="" />
            <el-option label="待支付" value="pending" />
            <el-option label="已取消" value="cancelled" />
            <el-option label="已支付" value="paid" />
          </el-select>
          <el-button plain @click="$router.push('/cart')">返回购物车</el-button>
        </div>
      </section>

      <section class="summary-grid">
        <div class="summary-card section-card">
          <span>订单总数</span>
          <strong>{{ orderList.length }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>待支付</span>
          <strong>{{ pendingCount }}</strong>
        </div>
      </section>

      <app-loading v-if="loading" />

      <section v-else class="order-list-wrap">
        <div v-if="orderList.length" class="order-grid">
          <article class="order-card section-card" v-for="order in orderList" :key="order.id">
            <div class="order-head">
              <div>
                <strong>{{ order.order_no }}</strong>
                <p>下单时间：{{ formatTime(order.created_at) }}</p>
              </div>
              <el-tag :type="statusType(order.status)">{{ statusLabel(order.status) }}</el-tag>
            </div>
            <div class="order-meta">
              <div class="meta-item">
                <span>订单ID</span><strong>{{ order.id }}</strong>
              </div>
              <div class="meta-item">
                <span>订单金额</span><strong>{{ formatPrice(order.total_amount) }}</strong>
              </div>
            </div>
            <div class="order-actions">
              <el-button type="primary" plain @click="openOrderDetail(order.id)">查看详情</el-button>
              <el-button
                v-if="order.status === 'pending'"
                type="success"
                plain
                :loading="payingOrderId === order.id"
                @click="handleStartPayment(order)"
                >去支付</el-button
              >
              <el-button v-if="order.status === 'pending'" type="danger" plain @click="handleCancelOrder(order.id)"
                >取消订单</el-button
              >
            </div>
          </article>
        </div>

        <div v-else class="empty-wrap section-card">
          <el-empty description="还没有订单记录，先去购物车提交订单吧">
            <el-button type="primary" @click="$router.push('/cart')">前往购物车</el-button>
          </el-empty>
        </div>
      </section>
    </main>

    <el-dialog title="订单详情" :visible.sync="detailVisible" width="860px">
      <div v-if="currentOrder" class="detail-panel">
        <div class="detail-top">
          <div class="detail-item">
            <span>订单号</span><strong>{{ currentOrder.order_no }}</strong>
          </div>
          <div class="detail-item">
            <span>状态</span><strong>{{ statusLabel(currentOrder.status) }}</strong>
          </div>
          <div class="detail-item">
            <span>总金额</span><strong>{{ formatPrice(currentOrder.total_amount) }}</strong>
          </div>
        </div>

        <el-table :data="currentOrder.items || []" border stripe>
          <el-table-column label="商品ID" prop="product_id" width="100" align="center" />
          <el-table-column label="商品名称" prop="product_name" min-width="200" />
          <el-table-column label="卖家ID" prop="seller_id" width="100" align="center" />
          <el-table-column label="单价" width="120" align="center">
            <template slot-scope="scope">{{ formatPrice(scope.row.price) }}</template>
          </el-table-column>
          <el-table-column label="数量" prop="quantity" width="100" align="center" />
          <el-table-column label="小计" width="120" align="center">
            <template slot-scope="scope">{{ formatPrice(scope.row.subtotal) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapState, mapGetters } from 'vuex'

export default {
  name: 'OrderList',
  components: { CommonHeader, AppLoading },
  data() {
    return {
      statusFilter: '',
      detailVisible: false,
      payingOrderId: null
    }
  },
  computed: {
    ...mapState('orderModule', ['orderList', 'currentOrder']),
    ...mapGetters('orderModule', ['pendingOrderCount', 'isOrderLoading']),
    loading() {
      return this.isOrderLoading
    },
    pendingCount() {
      return this.pendingOrderCount
    }
  },
  mounted() {
    this.fetchOrders()
  },
  methods: {
    ...mapActions('orderModule', ['fetchOrderList', 'fetchOrderDetail', 'cancelOrder', 'startPayment']),
    async fetchOrders() {
      await this.fetchOrderList({ status: this.statusFilter || undefined })
    },
    async openOrderDetail(orderId) {
      await this.fetchOrderDetail(orderId)
      this.detailVisible = true
    },
    async handleStartPayment(order) {
      if (!order || order.status !== 'pending') return
      this.payingOrderId = order.id
      try {
        const response = await this.startPayment(order.id)
        const payUrl = response && response.data && response.data.pay_url
        if (!payUrl) {
          this.$message.error('后端未返回银行支付地址')
          return
        }
        window.location.href = payUrl
      } finally {
        this.payingOrderId = null
      }
    },
    async handleCancelOrder(orderId) {
      try {
        await this.$confirm('确定要取消该订单吗？取消后库存会恢复。', '取消订单', {
          confirmButtonText: '取消订单',
          cancelButtonText: '返回',
          type: 'warning'
        })
        await this.cancelOrder(orderId)
        this.$message.success('订单已取消')
        await this.fetchOrders()
        if (this.currentOrder && this.currentOrder.id === orderId) {
          await this.fetchOrderDetail(orderId)
        }
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          // handled by interceptor
        }
      }
    },
    statusLabel(status) {
      const mapping = {
        pending: '待支付',
        cancelled: '已取消',
        paid: '已支付'
      }
      return mapping[status] || status
    },
    statusType(status) {
      const mapping = {
        pending: 'warning',
        cancelled: 'info',
        paid: 'success'
      }
      return mapping[status] || 'info'
    },
    formatPrice(value) {
      return `¥${Number(value || 0).toFixed(2)}`
    },
    formatTime(timeStr) {
      if (!timeStr) return '--'
      return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped lang="scss">
.page-head {
  padding: 24px;
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
  align-items: center;
}

.status-select {
  width: 180px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
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

.order-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 18px;
}

.order-card {
  padding: 22px;
}

.order-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.order-head strong {
  color: #111827;
  word-break: break-all;
}

.order-head p {
  margin: 8px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.order-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 18px;
}

.meta-item,
.detail-item {
  background: #f8fbff;
  border-radius: 16px;
  padding: 14px;
}

.meta-item span,
.detail-item span {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 6px;
}

.meta-item strong,
.detail-item strong {
  color: #111827;
}

.order-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-panel {
  display: grid;
  gap: 16px;
}

.detail-top {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media screen and (max-width: 960px) {
  .page-head,
  .head-actions {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid,
  .detail-top,
  .order-meta {
    grid-template-columns: 1fr;
  }

  .status-select {
    width: 100%;
  }
}
</style>
