<template>
  <div class="page-shell">
    <CommonHeader />
    <main class="page-main cart-management">
      <header class="management-heading">
        <h1>购物车管理</h1>
        <p v-if="!loading && !loadError">{{ total }} 个匹配账号</p>
      </header>

      <section class="section-card management-panel" aria-label="用户购物车列表">
        <form class="management-toolbar" @submit.prevent="search">
          <el-input v-model.trim="username" placeholder="用户名" aria-label="用户名" maxlength="64" clearable />
          <el-input v-model.trim="userId" placeholder="用户 ID" aria-label="用户 ID" inputmode="numeric" clearable />
          <el-button type="primary" native-type="submit">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </form>

        <AppLoading v-if="loading" />
        <ListError v-else-if="loadError" :message="loadError" @retry="fetchPage()" />
        <el-empty v-else-if="!owners.length" description="没有匹配的用户" />
        <template v-else>
          <table class="cart-owners">
            <thead>
              <tr>
                <th scope="col">用户</th>
                <th scope="col">商品种类</th>
                <th scope="col" class="wide-column">总件数</th>
                <th scope="col" class="action-column">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="owner in owners" :key="owner.user_id">
                <td>
                  <strong>{{ owner.username }}</strong>
                  <small
                    >#{{ owner.user_id }} · {{ roleLabels[owner.role] || owner.role
                    }}<template v-if="!owner.is_active"> · 已禁用</template></small
                  >
                </td>
                <td>{{ owner.item_count }}</td>
                <td class="wide-column">{{ owner.quantity_total }}</td>
                <td class="action-column">
                  <el-button text type="primary" @click="openCart(owner)">查看购物车</el-button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="total > pageSize" class="pagination-bar">
            <el-pagination
              :current-page="page"
              :page-size="pageSize"
              :total="total"
              :pager-count="5"
              layout="prev, pager, next"
              @current-change="fetchPage(appliedFilters, $event)"
            />
          </div>
        </template>
      </section>
    </main>

    <el-dialog
      v-model="detailOpen"
      :title="activeOwner ? activeOwner.username + ' 的购物车' : '购物车详情'"
      width="700px"
      destroy-on-close
      :show-close="!busy"
      :close-on-click-modal="!busy"
      :close-on-press-escape="!busy"
      @close="abortDetail"
    >
      <AppLoading v-if="detailLoading" />
      <ListError v-else-if="detailError" :message="detailError" @retry="loadCart" />
      <el-empty v-else-if="!cartItems.length" description="该用户的购物车为空" />
      <ul v-else class="managed-items">
        <li v-for="item in cartItems" :key="item.id" class="managed-row">
          <div class="item-meta">
            <strong>{{ item.product_name || '商品不可用' }}</strong>
            <small>商品 #{{ item.product_id }} · {{ item.selected ? '已勾选' : '未勾选' }}</small>
          </div>
          <div class="item-quantity">
            <span>数量 {{ item.quantity }}</span>
            <small v-if="item.status === 'on_sale'">库存 {{ item.stock }}</small>
            <small v-else>{{ item.status === 'off_shelf' ? '已下架' : '商品不存在' }}</small>
          </div>
          <div v-if="editingId === item.id" class="item-actions">
            <el-input-number
              v-model="editingQuantity"
              :min="1"
              :max="item.stock"
              :step-strictly="true"
              :disabled="busy"
              size="small"
              :aria-label="item.product_name + ' 的数量'"
            />
            <el-button
              plain
              type="primary"
              size="small"
              :disabled="busy || !Number.isInteger(editingQuantity) || editingQuantity === item.quantity"
              @click="saveQuantity(item)"
              >保存数量</el-button
            >
            <el-button text size="small" :disabled="busy" @click="editingId = null">取消</el-button>
          </div>
          <div v-else class="item-actions">
            <el-button
              text
              type="primary"
              :disabled="busy || item.status !== 'on_sale' || item.stock < 1"
              @click="editQuantity(item)"
              >调整数量</el-button
            >
            <el-button text type="danger" :disabled="busy" @click="removeItem(item)">移除</el-button>
          </div>
        </li>
      </ul>

      <template #footer>
        <el-button :disabled="busy" @click="detailOpen = false">关闭</el-button>
        <el-button
          v-if="cartItems.length && !detailLoading && !detailError"
          plain
          type="danger"
          :disabled="busy"
          @click="clearCart"
          >清空购物车</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import CommonHeader from '@/components/CommonHeader.vue'
import AppLoading from '@/components/AppLoading.vue'
import ListError from '@/components/ListError.vue'
import {
  clearManagedCart,
  getCartOwners,
  getManagedCart,
  removeManagedCartItem,
  updateManagedCartQuantity
} from '@/services/cartService'
import message from '@/utils/message'
import { usePagedList } from '@/utils/usePagedList'

const {
  items: owners,
  loading,
  loadError,
  page,
  pageSize,
  total,
  appliedFilters,
  fetchPage
} = usePagedList(getCartOwners, 'owners')
const roleLabels = { user: '普通用户', merchant: '商户', admin: '管理员', auditor: '审计员' }
const username = ref('')
const userId = ref('')
const activeOwner = ref(null)
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const cartItems = ref([])
const editingId = ref(null)
const editingQuantity = ref(1)
const busy = ref(false)
let detailRequest
let disposed = false

function search() {
  return fetchPage({ username: username.value || undefined, user_id: userId.value || undefined }, 1)
}

function reset() {
  username.value = ''
  userId.value = ''
  return fetchPage({}, 1)
}

function abortDetail() {
  detailRequest?.abort()
  detailRequest = undefined
}

async function loadCart() {
  if (!activeOwner.value) return
  abortDetail()
  const controller = new AbortController()
  detailRequest = controller
  detailLoading.value = true
  detailError.value = ''
  try {
    const response = await getManagedCart(activeOwner.value.user_id, { signal: controller.signal, silentError: true })
    if (controller.signal.aborted) return
    activeOwner.value = response.data.owner
    cartItems.value = response.data.items
  } catch (error) {
    if (!controller.signal.aborted) {
      detailError.value = error.response?.data?.message || '购物车加载失败，请重试。'
    }
  } finally {
    if (detailRequest === controller) {
      detailRequest = undefined
      detailLoading.value = false
    }
  }
}

function openCart(owner) {
  activeOwner.value = owner
  cartItems.value = []
  editingId.value = null
  detailOpen.value = true
  return loadCart()
}

function editQuantity(item) {
  editingId.value = item.id
  editingQuantity.value = Math.min(item.quantity, item.stock)
}

async function modifyCart(operation, confirmation) {
  if (busy.value || !activeOwner.value) return
  busy.value = true
  const owner = activeOwner.value
  try {
    if (confirmation) {
      await ElMessageBox.confirm(confirmation, '确认修改购物车', {
        type: 'warning',
        confirmButtonText: '确认',
        cancelButtonText: '取消'
      })
    }
    if (disposed) return
    const response = await operation(owner.user_id)
    if (disposed) return
    message.success(response.message)
    editingId.value = null
    await Promise.all([loadCart(), fetchPage()])
  } catch {
    // The request interceptor displays write errors.
  } finally {
    busy.value = false
  }
}

function saveQuantity(item) {
  const quantity = editingQuantity.value
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > item.stock || quantity === item.quantity) return
  return modifyCart((ownerId) => updateManagedCartQuantity(ownerId, item.id, quantity))
}

function removeItem(item) {
  const name = item.product_name || '商品 #' + item.product_id
  return modifyCart(
    (ownerId) => removeManagedCartItem(ownerId, item.id),
    '确定从 ' + activeOwner.value.username + ' 的购物车移除「' + name + '」吗？'
  )
}

function clearCart() {
  return modifyCart(clearManagedCart, '确定清空 ' + activeOwner.value.username + ' 的购物车吗？')
}

fetchPage()
onBeforeUnmount(() => {
  disposed = true
  abortDetail()
})
</script>

<style scoped>
.cart-management {
  max-width: 1080px;
}
.management-heading {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-bottom: 16px;
}
.management-heading h1 {
  font-size: clamp(24px, 4vw, 34px);
  margin: 0;
}
.management-heading p {
  margin: 0;
  color: var(--mall-muted);
  font-size: 14px;
}
.management-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px;
}
.management-toolbar .el-input {
  flex: 0 1 168px;
  min-width: 0;
}
.management-toolbar .el-button,
.item-actions .el-button {
  margin: 0;
}
.management-panel {
  padding-bottom: 10px;
}
.cart-owners {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 14px;
}
.cart-owners th,
.cart-owners td {
  padding: 10px 14px;
  border-top: 1px solid var(--mall-border);
}
.cart-owners th {
  background: #faf8f4;
  color: var(--mall-muted);
  font-size: 13px;
}
.cart-owners td {
  overflow-wrap: anywhere;
}
.cart-owners small,
.item-meta small,
.item-quantity small {
  display: block;
  margin-top: 4px;
  color: var(--mall-muted);
}
.action-column {
  width: 1%;
  white-space: nowrap;
}
.managed-items {
  list-style: none;
  padding: 0;
  margin: 0;
}
.managed-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(72px, auto) minmax(0, auto);
  gap: 12px;
  align-items: center;
  padding: 12px 0;
}
.managed-row + .managed-row {
  border-top: 1px solid var(--mall-border);
}
.item-meta {
  min-width: 0;
  overflow-wrap: anywhere;
}
.item-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.item-actions :deep(.el-input-number) {
  width: 104px;
}
@media (max-width: 620px) {
  .wide-column {
    display: none;
  }
  .management-toolbar .el-input {
    flex: 1 1 105px;
  }
  .cart-owners th,
  .cart-owners td {
    padding-inline: 8px;
  }
  .managed-row {
    grid-template-columns: minmax(0, 1fr) minmax(65px, auto);
    gap: 8px;
  }
  .item-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>
