<template>
  <div class="page-shell pay-result-page">
    <common-header />

    <main class="page-main pay-result-main">
      <section class="section-card result-card">
        <el-result :icon="resultIcon" :title="resultTitle" :sub-title="resultMessage">
          <template slot="extra">
            <el-descriptions :column="1" border class="result-desc">
              <el-descriptions-item label="订单号">{{ orderNo || '--' }}</el-descriptions-item>
              <el-descriptions-item label="银行流水号">{{ bankTradeNo || '--' }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ status || '--' }}</el-descriptions-item>
            </el-descriptions>

            <div v-if="!isAuthenticated" class="login-tip">
              当前登录状态可能已丢失，但支付结果已返回。重新登录后可查看订单状态。
            </div>

            <div class="result-actions">
              <el-button type="primary" @click="goOrders">查看订单</el-button>
              <el-button plain @click="$router.push('/home')">继续购物</el-button>
            </div>
          </template>
        </el-result>
      </section>
    </main>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import { mapActions, mapState } from 'vuex'

export default {
  name: 'PayResult',
  components: { CommonHeader },

  computed: {
    ...mapState('authModule', ['isAuthenticated']),

    status() {
      return this.$route.query.status || ''
    },

    orderNo() {
      return this.$route.query.order_no || ''
    },

    bankTradeNo() {
      return this.$route.query.bank_trade_no || ''
    },

    resultIcon() {
      return this.status === 'SUCCESS' ? 'success' : 'error'
    },

    resultTitle() {
      return this.status === 'SUCCESS' ? '支付成功' : '支付失败'
    },

    resultMessage() {
      return this.$route.query.message || '银行已返回支付结果，请稍后在订单列表确认最终状态。'
    }
  },

  mounted() {
    // 只有仍然保持登录态时才刷新订单列表，避免 401 后被 apiClient 强制踢回登录页
    if (this.isAuthenticated) {
      this.fetchOrderList().catch(() => {})
    }
  },

  methods: {
    ...mapActions('orderModule', ['fetchOrderList']),

    goOrders() {
      if (this.isAuthenticated) {
        this.$router.push('/orders')
      } else {
        this.$router.push('/user-login')
      }
    }
  }
}
</script>

<style scoped lang="scss">
.pay-result-main {
  max-width: 880px;
}

.result-card {
  padding: 28px;
}

.result-desc {
  margin: 18px auto 22px;
  max-width: 620px;
  text-align: left;
}

.login-tip {
  margin: 0 auto 18px;
  max-width: 620px;
  color: #e6a23c;
  font-size: 14px;
  text-align: center;
}

.result-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}
</style>
