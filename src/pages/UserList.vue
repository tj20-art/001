<template>
  <div class="page-shell user-admin-page">
    <common-header />

    <main class="list-main page-main">
      <section class="header-card section-card">
        <div>
          <h1>用户管理</h1>
          <p>分配管理员、商户、普通用户和审计员角色，并检查特权账号的 MFA 状态。</p>
        </div>
        <el-tag type="warning">管理员专属</el-tag>
      </section>

      <section class="toolbar-card section-card">
        <div class="toolbar-row">
          <el-input v-model.number="searchParams.user_id" placeholder="输入用户ID" class="search-input" clearable />
          <el-input v-model="searchParams.username" placeholder="输入用户名" class="search-input" clearable />
          <el-input v-model="searchParams.phone" placeholder="输入手机号" class="search-input" clearable />
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </div>
      </section>

      <app-loading v-if="loading" />

      <section v-else class="table-card section-card">
        <el-table :data="userList" border stripe style="width: 100%">
          <el-table-column label="用户ID" prop="id" width="100" align="center" />
          <el-table-column label="用户名" prop="username" min-width="160" />
          <el-table-column label="手机号" prop="phone" min-width="160" />
          <el-table-column label="角色与权限" min-width="250">
            <template slot-scope="scope">
              <div class="role-cell">
                <el-select
                  :value="scope.row.role"
                  size="small"
                  :disabled="isCurrentUser(scope.row)"
                  @change="handleRoleChange(scope.row, $event)"
                >
                  <el-option v-for="role in roleOptions" :key="role.value" :label="role.label" :value="role.value" />
                </el-select>
                <el-tag
                  v-if="['admin', 'auditor'].includes(scope.row.role)"
                  size="mini"
                  :type="scope.row.totp_enabled ? 'success' : 'danger'"
                >
                  {{ scope.row.totp_enabled ? 'MFA 已绑定' : '待绑定 MFA' }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="180">
            <template slot-scope="scope">{{ formatTime(scope.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="300" align="center" fixed="right">
            <template slot-scope="scope">
              <el-button type="text" :disabled="isCurrentUser(scope.row)" @click="openResetDialog(scope.row)">
                重置信息
              </el-button>
              <el-button
                v-if="isMfaRole(scope.row.role)"
                type="text"
                class="mfa-reset-button"
                :disabled="isCurrentUser(scope.row) || !scope.row.totp_enabled"
                @click="handleResetMfa(scope.row)"
              >
                {{ scope.row.totp_enabled ? '重置 2FA' : '2FA 未绑定' }}
              </el-button>
              <el-button
                type="text"
                :disabled="isCurrentUser(scope.row)"
                :style="{ color: isCurrentUser(scope.row) ? '#cbd5e1' : '#ef4444' }"
                @click="handleDeleteUser(scope.row.id)"
              >
                {{ isCurrentUser(scope.row) ? '当前账号' : '禁用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="empty-wrap" v-if="!userList.length">
          <el-empty description="暂无匹配用户" />
        </div>
      </section>

      <el-dialog
        :title="resetTarget ? `重置 ${resetTarget.username} 的账号信息` : '重置账号信息'"
        :visible.sync="resetDialogVisible"
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
        <el-form label-position="top" @submit.native.prevent>
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
        <span slot="footer" class="dialog-footer">
          <el-button @click="resetDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="resetSubmitting" @click="submitUserReset">确认重置</el-button>
        </span>
      </el-dialog>
    </main>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapState, mapGetters } from 'vuex'

export default {
  name: 'UserList',
  components: { CommonHeader, AppLoading },
  data() {
    return {
      loading: true,
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
    ...mapState('userModule', ['userList']),
    ...mapGetters('authModule', ['isAdmin', 'userId'])
  },
  mounted() {
    this.checkAdminPermission()
    this.fetchUserListData()
  },
  methods: {
    ...mapActions('userModule', ['getUserList', 'deleteUser', 'updateUserRole', 'adminResetUserInfo', 'resetUserMfa']),
    checkAdminPermission() {
      if (!this.isAdmin) {
        this.$message.error('权限不足，仅管理员可访问用户管理')
        this.$router.push(this.userId ? `/profile/${this.userId}` : '/user-login')
      }
    },
    async fetchUserListData(params = {}) {
      this.loading = true
      try {
        await this.getUserList(params)
      } finally {
        this.loading = false
      }
    },
    async handleSearch() {
      await this.fetchUserListData({
        user_id: this.searchParams.user_id || undefined,
        name: this.searchParams.username || undefined,
        phone: this.searchParams.phone || undefined
      })
    },
    handleReset() {
      this.searchParams = { user_id: '', username: '', phone: '' }
      this.fetchUserListData()
    },
    async handleDeleteUser(userId) {
      try {
        await this.$confirm('确定要禁用该用户吗？禁用后将无法继续登录。', '禁用用户', {
          confirmButtonText: '禁用',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.deleteUser(userId)
        this.$message.success('用户已禁用')
        this.handleSearch()
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          // handled by interceptor
        }
      }
    },
    async handleRoleChange(user, role) {
      try {
        await this.$confirm(`确定将 ${user.username} 的角色调整为“${this.roleLabel(role)}”吗？`, '调整角色', {
          confirmButtonText: '确认调整',
          cancelButtonText: '取消',
          type: 'warning'
        })
        await this.updateUserRole({ userId: user.id, role })
        this.$message.success('角色更新成功')
        await this.handleSearch()
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          await this.handleSearch()
        }
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
        await this.handleSearch()
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
        await this.handleSearch()
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

<style scoped lang="scss">
.list-main {
  max-width: 1280px;
}

.header-card,
.toolbar-card,
.table-card {
  padding: 24px;
}

.header-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;

  h1 {
    margin: 0 0 10px;
    font-size: 30px;
    color: #111827;
  }

  p {
    margin: 0;
    color: #6b7280;
  }
}

.toolbar-card {
  margin-bottom: 18px;
}

.toolbar-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.search-input {
  width: 220px;
}

.role-cell {
  display: flex;
  align-items: center;
  gap: 10px;

  .el-select {
    width: 122px;
  }
}

.mfa-reset-button {
  color: #d97706;
}

.reset-alert {
  margin-bottom: 20px;
}

.password-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.field-hint {
  margin-top: 6px;
  color: #8492a6;
  font-size: 12px;
  line-height: 1.6;
}

@media screen and (max-width: 960px) {
  .header-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .search-input {
    width: 100%;
  }

  .password-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
