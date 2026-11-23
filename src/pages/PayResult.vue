<template>
  <div class="page-shell">
    <CommonHeader />
    <main class="page-main pay-result-main">
      <section class="section-card result-card">
        <el-result :icon="result.icon" :title="result.title" :sub-title="result.message">
          <template #extra>
            <p v-if="orderNo" class="order-reference">订单号 {{ orderNo }}</p>
            <div class="result-actions">
              <el-button v-if="!isAuthenticated && orderNo" type="primary" @click="signIn">登录查看状态</el-button>
              <el-button v-else-if="orderId" type="primary" @click="goOrders">查看订单</el-button>
              <el-button v-if="isAuthenticated && orderNo && canRetry" plain @click="checkStatus"> 重新查询 </el-button>
              <el-button plain @click="$router.push('/home')">继续购物</el-button>
            </div>
          </template>
        </el-result>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStore } from 'vuex'
import CommonHeader from '@/components/CommonHeader.vue'
import { getOrderStatus } from '@/services/orderService'

const route = useRoute()
const router = useRouter()
const store = useStore()
const orderNo = computed(() => (typeof route.query.order_no === 'string' ? route.query.order_no : ''))
const isAuthenticated = computed(() => store.state.authModule.isAuthenticated)
const orderId = ref(null)
const state = ref('waiting')
let activeRequest
let timer

const results = {
  waiting: { icon: 'info', title: '支付确认中', message: '正在查询商城订单的入账状态。' },
  pending: { icon: 'info', title: '仍在等待确认', message: '可重新查询，或稍后在我的订单查看。' },
  paid: { icon: 'success', title: '支付成功', message: '商城订单已确认入账。' },
  cancelled: { icon: 'warning', title: '订单已取消', message: '请在我的订单查看详情。' },
  unavailable: { icon: 'warning', title: '暂时无法确认', message: '请重新查询或前往我的订单。' },
  missing: { icon: 'warning', title: '无法查询这笔订单', message: '请在我的订单查看支付状态。' },
  signed_out: { icon: 'info', title: '支付结果待确认', message: '登录后可查询这笔订单的状态。' }
}
const result = computed(() => results[state.value])
const canRetry = computed(() => ['pending', 'unavailable'].includes(state.value))

function stopChecking() {
  clearTimeout(timer)
  activeRequest?.abort()
  activeRequest = undefined
}

async function poll(controller, attemptsLeft) {
  try {
    const response = await getOrderStatus(orderNo.value, { signal: controller.signal, silentError: true })
    if (controller.signal.aborted) return
    const order = response.data?.order
    orderId.value = order?.id ?? null
    if (order?.status === 'paid' || order?.status === 'cancelled') {
      state.value = order.status
    } else if (attemptsLeft > 1) {
      timer = setTimeout(() => poll(controller, attemptsLeft - 1), 2500)
    } else {
      state.value = 'pending'
    }
  } catch (error) {
    if (!controller.signal.aborted) state.value = error.response?.status === 404 ? 'missing' : 'unavailable'
  }
}

function checkStatus() {
  stopChecking()
  orderId.value = null
  if (!orderNo.value) {
    state.value = 'missing'
    return
  }
  if (!isAuthenticated.value) {
    state.value = 'signed_out'
    return
  }
  state.value = 'waiting'
  const controller = new AbortController()
  activeRequest = controller
  poll(controller, 10)
}

function signIn() {
  router.push({ path: '/user-login', query: { redirect: route.fullPath } })
}
function goOrders() {
  router.push({ path: '/orders', query: { order: orderId.value } })
}

watch([orderNo, isAuthenticated], checkStatus, { immediate: true })
onBeforeUnmount(stopChecking)
</script>

<style scoped>
.pay-result-main {
  max-width: 740px;
}
.result-card {
  padding: 16px;
}
.order-reference {
  overflow-wrap: anywhere;
  color: var(--mall-muted);
}
.result-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.result-actions :deep(.el-button) {
  margin: 0;
}
</style>
