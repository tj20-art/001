<template>
  <div class="page-shell user-admin-page">
    <common-header />

    <main class="list-main page-main">
      <header class="user-heading">
        <h1>用户管理</h1>
      </header>
      <section class="section-card user-list" aria-label="用户列表">
        <form class="user-toolbar" @submit.prevent="handleSearch">
          <el-input v-model.trim="searchParams.username" aria-label="用户名" placeholder="用户名" clearable />
          <el-input v-model.trim="searchParams.user_id" aria-label="用户 ID" placeholder="用户 ID" clearable />
          <el-input v-model.trim="searchParams.phone" aria-label="手机号" placeholder="手机号" clearable />
          <el-button type="primary" native-type="submit">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </form>
        <AppLoading v-if="loading" />
        <ListError v-else-if="loadError" :message="loadError" @retry="fetchUserListData()" />
        <el-empty v-else-if="!userList.length" description="暂无匹配用户" />
        <table v-else class="user-table">
          <thead>
            <tr>
              <th scope="col">用户</th>
              <th scope="col" class="desktop-column">手机号</th>
              <th scope="col">角色与状态</th>
              <th scope="col" class="desktop-column">创建时间</th>
              <th scope="col" class="user-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in userList" :key="user.id">
              <td>
                <strong>{{ user.username }}</strong
                ><small>#{{ user.id }}</small>
              </td>
              <td class="desktop-column">{{ user.phone }}</td>
              <td>
                <div class="desktop-role">
                  <el-select
                    :model-value="user.role"
                    :disabled="isCurrentUser(user) || !user.is_active || !!changingRoleId"
                    :aria-label="user.username + ' 的角色'"
                    size="small"
                    @change="handleRoleChange(user, $event)"
                  >
                    <el-option v-for="role in roleOptions" :key="role.value" :label="role.label" :value="role.value" />
                  </el-select>
                </div>
                <span class="mobile-role">{{ roleLabel(user.role) }}</span>
                <small v-if="!user.is_active">已禁用</small>
                <small v-else-if="isMfaRole(user.role)">{{ user.totp_enabled ? 'MFA 已绑定' : '待绑定 MFA' }}</small>
              </td>
              <td class="desktop-column">{{ formatTime(user.created_at) }}</td>
              <td class="user-actions">
                <el-button text type="primary" @click="openUserDetails(user)">详情</el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <el-dialog v-model="detailsVisible" title="用户详情" width="500px">
        <div v-if="detailUser" class="account-details">
          <h2>{{ detailUser.username }}</h2>
          <dl>
            <div>
              <dt>用户 ID</dt>
              <dd>{{ detailUser.id }}</dd>
            </div>
            <div>
              <dt>手机号</dt>
              <dd>{{ detailUser.phone }}</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>{{ detailUser.is_active ? '正常' : '已禁用' }}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{{ formatTime(detailUser.created_at) }}</dd>
            </div>
            <div v-if="isMfaRole(detailUser.role)">
              <dt>MFA</dt>
              <dd>{{ detailUser.totp_enabled ? '已绑定' : '待绑定' }}</dd>
            </div>
          </dl>
          <el-select
            :model-value="detailUser.role"
            :disabled="isCurrentUser(detailUser) || !detailUser.is_active || !!changingRoleId"
            aria-label="调整用户角色"
            @change="handleRoleChange(detailUser, $event)"
          >
            <el-option v-for="role in roleOptions" :key="role.value" :label="role.label" :value="role.value" />
          </el-select>
          <div v-if="!isCurrentUser(detailUser) && detailUser.is_active" class="account-actions">
            <el-button plain @click="openResetDialog(detailUser)">重置信息</el-button>
            <el-button
              v-if="isMfaRole(detailUser.role) && detailUser.totp_enabled"
              plain
              @click="handleResetMfa(detailUser)"
              >重置 2FA</el-button
            >
            <el-button plain type="danger" @click="handleDeleteUser(detailUser.id)">禁用用户</el-button>
          </div>
        </div>
      </el-dialog>

      <el-dialog
        :title="resetTarget ? `重置 ${resetTarget.username} 的账号信息` : '重置账号信息'"
        v-model="resetDialogVisible"
        width="560px"
        :close-on-click-modal="false"
        @closed="clearResetForm"
      >
        <el-alert
          title="保存后会强制该用户重新登录"
          description="可修改用户名、手机号，或设置临时密码。修改用户名时系统会自动签发并下载一份新登录证书。"
          type="warning"
          :closable="false"
          show-icon
          class="reset-alert"
        />
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="用户名">
            <el-input v-model.trim="resetForm.username" maxlength="20" show-word-limit />
            <div class="field-hint">5–20 位字母、数字或下划线；修改后旧证书立即失效。</div>
          </el-form-item>
          <el-form-item label="手机号">
            <el-input v-model.trim="resetForm.phone" maxlength="11" />
          </el-form-item>
          <div class="password-grid">
            <el-form-item label="临时密码（选填）">
              <el-input
                v-model="resetForm.new_password"
                type="password"
                autocomplete="new-password"
                show-password
                placeholder="不填写则保留原密码"
              />
            </el-form-item>
            <el-form-item label="确认临时密码">
              <el-input
                v-model="resetForm.confirm_password"
                type="password"
                autocomplete="new-password"
                show-password
                placeholder="再次输入临时密码"
              />
            </el-form-item>
          </div>
          <div class="field-hint">密码需为 8–20 位，并同时包含大小写字母、数字和特殊符号。</div>
        </el-form>
        <template #footer>
          <el-button @click="resetDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="resetSubmitting" @click="submitUserReset">确认重置</el-button>
        </template>
      </el-dialog>
    </main>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader.vue'
import AppLoading from '@/components/AppLoading.vue'
import { mapActions, mapGetters } from 'vuex'
import ListError from '@/components/ListError.vue'
import { getUserList } from '@/services/userService'

export default {
  name: 'UserList',
  components: { CommonHeader, AppLoading, ListError },
  data() {
    return {
      loading: true,
      userList: [],
      activeFilters: {},
      loadError: '',
      requestSequence: 0,
      detailsVisible: false,
      detailsUserId: null,
      changingRoleId: null,
      resetDialogVisible: false,
      resetSubmitting: false,
      resetTarget: null,
      resetForm: {
        username: '',
        phone: '',
        new_password: '',
        confirm_password: ''
      },
      searchParams: {
        user_id: '',
        username: '',
        phone: ''
      },
      roleOptions: [
        { value: 'user', label: '普通用户' },
        { value: 'merchant', label: '商户' },
        { value: 'admin', label: '管理员' },
        { value: 'auditor', label: '审计员' }
      ]
    }
  },
  computed: {
    ...mapGetters('authModule', ['userId']),
    detailUser() {
      return this.userList.find((user) => user.id === this.detailsUserId)
    }
  },
  mounted() {
    this.fetchUserListData()
  },
  beforeUnmount() {
    this.requestSequence += 1
  },
  methods: {
    ...mapActions('userModule', ['deleteUser', 'updateUserRole', 'adminResetUserInfo', 'resetUserMfa']),
    async fetchUserListData(filters = this.activeFilters) {
      const sequence = ++this.requestSequence
      this.activeFilters = { ...filters }
      this.loading = true
      this.loadError = ''
      try {
        const response = await getUserList(filters, { silentError: true })
        if (sequence === this.requestSequence) this.userList = response.data?.user_list || []
      } catch (error) {
        if (sequence === this.requestSequence) {
          this.loadError = error.response?.data?.message || '用户列表加载失败，请重试。'
        }
      } finally {
        if (sequence === this.requestSequence) this.loading = false
      }
    },
    handleSearch() {
      return this.fetchUserListData({
        user_id: this.searchParams.user_id || undefined,
        name: this.searchParams.username || undefined,
        phone: this.searchParams.phone || undefined
      })
    },
    handleReset() {
      this.searchParams = { user_id: '', username: '', phone: '' }
      return this.fetchUserListData({})
    },
    openUserDetails(user) {
      this.detailsUserId = user.id
      this.detailsVisible = true
    },
    async handleDeleteUser(userId) {
      try {
        await this.$confirm('确定要禁用该用户吗？禁用后将无法继续登录。', '禁用用户', {
          confirmButtonText: '禁用',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.deleteUser(userId)
        this.detailsVisible = false
        this.$message.success('用户已禁用')
        this.fetchUserListData()
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          // handled by interceptor
        }
      }
    },
    async handleRoleChange(user, role) {
      if (user.role === role || this.changingRoleId) return
      this.changingRoleId = user.id
      try {
        await this.$confirm('确定将 ' + user.username + ' 的角色调整为“' + this.roleLabel(role) + '”吗？', '调整角色', {
          confirmButtonText: '确认调整',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.updateUserRole({ userId: user.id, role })
        this.$message.success('角色已更新，该用户需重新登录')
        await this.fetchUserListData()
      } catch {
        // The API client reports update errors.
      } finally {
        this.changingRoleId = null
      }
    },
    isCurrentUser(user) {
      return Number(user.id) === Number(this.userId)
    },
    isMfaRole(role) {
      return ['admin', 'auditor'].includes(role)
    },
    openResetDialog(user) {
      if (this.isCurrentUser(user)) return
      this.detailsVisible = false
      this.resetTarget = { ...user }
      this.resetForm = {
        username: user.username || '',
        phone: user.phone || '',
        new_password: '',
        confirm_password: ''
      }
      this.resetDialogVisible = true
    },
    clearResetForm() {
      this.resetTarget = null
      this.resetForm = { username: '', phone: '', new_password: '', confirm_password: '' }
      this.resetSubmitting = false
    },
    validateResetForm() {
      if (!/^[a-zA-Z0-9_]{5,20}$/.test(this.resetForm.username)) {
        return '用户名需为 5–20 位字母、数字或下划线'
      }
      if (!/^1[3-9]\d{9}$/.test(this.resetForm.phone)) {
        return '请输入有效的 11 位手机号'
      }
      if (this.resetForm.new_password) {
        const passwordPattern = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()+=-]).{8,20}$/
        if (!passwordPattern.test(this.resetForm.new_password)) {
          return '临时密码必须包含大小写字母、数字和特殊符号，长度为 8–20 位'
        }
        if (this.resetForm.new_password !== this.resetForm.confirm_password) {
          return '两次输入的临时密码不一致'
        }
      }
      return ''
    },
    async submitUserReset() {
      const validationMessage = this.validateResetForm()
      if (validationMessage) {
        this.$message.warning(validationMessage)
        return
      }

      const userData = {}
      if (this.resetForm.username !== this.resetTarget.username) userData.username = this.resetForm.username
      if (this.resetForm.phone !== this.resetTarget.phone) userData.phone = this.resetForm.phone
      if (this.resetForm.new_password) userData.new_password = this.resetForm.new_password
      if (!Object.keys(userData).length) {
        this.$message.info('没有需要重置的内容')
        return
      }

      this.resetSubmitting = true
      try {
        const response = await this.adminResetUserInfo({ userId: this.resetTarget.id, userData })
        const certificate = response.data && response.data.replacement_certificate
        if (certificate) this.downloadReplacementCertificate(certificate)
        this.$message.success(certificate ? '信息已重置，新用户证书已下载' : '用户信息已重置')
        this.resetDialogVisible = false
        await this.fetchUserListData()
      } finally {
        this.resetSubmitting = false
      }
    },
    downloadReplacementCertificate(certificate) {
      const blob = new Blob([certificate.pem], { type: 'application/x-pem-file' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = certificate.filename || 'user_certificate.crt'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.setTimeout(() => window.URL.revokeObjectURL(url), 0)
    },
    async handleResetMfa(user) {
      try {
        await this.$confirm(
          `确定重置 ${user.username} 的双因素认证吗？旧密钥和所有恢复码会立即失效，该用户下次登录必须重新扫码绑定。`,
          '重置 2FA',
          {
            confirmButtonText: '确认重置',
            cancelButtonText: '取消',
            type: 'warning'
          }
        )
        await this.resetUserMfa(user.id)
        this.$message.success('2FA 已重置，用户下次登录需重新绑定')
        await this.fetchUserListData()
      } catch (error) {
        if (error !== 'cancel' && (!error || error.message !== 'cancel')) {
          // API errors are handled by the response interceptor.
        }
      }
    },
    roleLabel(role) {
      return this.roleOptions.find((item) => item.value === role)?.label || role
    },
    formatTime(timeStr) {
      if (!timeStr) return '--'
      return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped>
.user-heading h1 {
  margin: 0 0 16px;
  font-size: clamp(22px, 4vw, 32px);
}
.user-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 14px;
}
.user-toolbar :deep(.el-input) {
  width: 156px;
}
.user-toolbar :deep(.el-button),
.account-actions :deep(.el-button) {
  margin: 0;
}
.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  text-align: left;
}
.user-table th,
.user-table td {
  padding: 10px 12px;
  border-top: 1px solid var(--mall-border);
}
.user-table th {
  background: #faf8f4;
  color: var(--mall-muted);
  font-size: 13px;
}
.user-table td {
  overflow-wrap: anywhere;
}
.user-table small {
  display: block;
  margin-top: 4px;
  color: var(--mall-muted);
}
.user-actions {
  width: 1%;
  white-space: nowrap;
}
.desktop-role :deep(.el-select) {
  max-width: 136px;
}
.mobile-role {
  display: none;
}
.account-details h2 {
  margin: 0 0 14px;
  overflow-wrap: anywhere;
}
.account-details dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.account-details dd {
  margin: 3px 0 0;
  overflow-wrap: anywhere;
  font-weight: 600;
}
.account-details dt,
.field-hint {
  color: var(--mall-muted);
  font-size: 13px;
}
.account-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.reset-alert {
  margin-bottom: 12px;
}
.password-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 680px) {
  .desktop-column,
  .desktop-role {
    display: none;
  }
  .mobile-role {
    display: block;
  }
  .user-toolbar :deep(.el-input) {
    flex: 1 1 104px;
    min-width: 0;
  }
  .user-table th,
  .user-table td {
    padding: 8px 6px;
  }
  .password-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
