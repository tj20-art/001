<template>
  <div class="page-shell security-page">
    <common-header />

    <main class="security-main page-main">
      <section class="security-hero">
        <div>
          <span class="eyebrow">SECURITY OPERATIONS</span>
          <h1>安全审计中心</h1>
          <p>集中查看角色权限边界、身份验证结果与敏感操作记录。</p>
        </div>
        <div class="hero-badge">
          <i class="el-icon-lock"></i>
          <div>
            <strong>国密安全链路</strong>
            <span>SM2 + SM4-GCM · HTTPS</span>
          </div>
        </div>
      </section>

      <app-loading v-if="loading" />

      <template v-else>
        <el-alert v-if="loadError" class="page-alert" :title="loadError" type="error" :closable="false" show-icon />

        <section class="stats-grid">
          <article class="stat-card">
            <span class="stat-icon blue"><i class="el-icon-user-solid"></i></span>
            <div>
              <strong>{{ roleEntries.length }}</strong
              ><span>系统角色</span>
            </div>
          </article>
          <article class="stat-card">
            <span class="stat-icon violet"><i class="el-icon-key"></i></span>
            <div>
              <strong>{{ permissionCount }}</strong
              ><span>权限规则</span>
            </div>
          </article>
          <article class="stat-card">
            <span class="stat-icon green"><i class="el-icon-document-checked"></i></span>
            <div>
              <strong>{{ auditLogs.length }}</strong
              ><span>当前审计记录</span>
            </div>
          </article>
          <article class="stat-card">
            <span class="stat-icon red"><i class="el-icon-warning-outline"></i></span>
            <div>
              <strong>{{ deniedCount }}</strong
              ><span>失败或拒绝</span>
            </div>
          </article>
        </section>

        <section class="section-card matrix-section">
          <div class="section-heading">
            <div>
              <span class="eyebrow">ACCESS CONTROL</span>
              <h2>角色权限矩阵</h2>
              <p>前端展示用于辅助理解，最终权限始终由后端资源级鉴权决定。</p>
            </div>
            <el-button icon="el-icon-refresh" round @click="loadAll">刷新</el-button>
          </div>

          <div class="role-grid">
            <article v-for="role in roleEntries" :key="role.key" class="role-card" :class="`role-${role.key}`">
              <header>
                <span class="role-avatar">{{ role.short }}</span>
                <div>
                  <h3>{{ role.label }}</h3>
                  <span>{{ role.key }}</span>
                </div>
                <el-tag size="small" :type="role.tagType">{{ role.permissions.length }} 项权限</el-tag>
              </header>
              <p>{{ role.description }}</p>
              <div class="permission-list">
                <span v-for="permission in role.permissions" :key="permission">
                  <i class="el-icon-check"></i>{{ formatPermission(permission) }}
                </span>
              </div>
            </article>
          </div>
        </section>

        <section class="section-card audit-section">
          <div class="section-heading audit-heading">
            <div>
              <span class="eyebrow">AUDIT TRAIL</span>
              <h2>安全事件记录</h2>
              <p>只记录必要的主体、资源与结果，不保存密码、验证码和私钥正文。</p>
            </div>
            <el-button type="primary" icon="el-icon-download" round :loading="exporting" @click="handleExport">
              导出 CSV
            </el-button>
          </div>

          <div class="filter-bar">
            <el-input v-model.trim="filters.event_type" clearable placeholder="事件类型，如 AUTH_LOGIN" />
            <el-select v-model="filters.result" clearable placeholder="执行结果">
              <el-option label="成功" value="success" />
              <el-option label="拒绝" value="denied" />
              <el-option label="失败" value="failure" />
            </el-select>
            <el-input v-model.trim="filters.user_id" clearable placeholder="用户 ID" />
            <el-button type="primary" icon="el-icon-search" @click="loadAuditLogs">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </div>

          <el-table v-if="auditLogs.length" :data="auditLogs" stripe class="audit-table">
            <el-table-column prop="created_at" label="时间" min-width="155" />
            <el-table-column label="操作者" min-width="130">
              <template slot-scope="scope">
                <div class="operator-cell">
                  <strong>{{ scope.row.username || '匿名请求' }}</strong>
                  <span>{{ roleLabel(scope.row.role) }} · ID {{ scope.row.user_id || '-' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="event_type" label="事件" min-width="190" show-overflow-tooltip />
            <el-table-column label="操作" width="92">
              <template slot-scope="scope"
                ><code>{{ String(scope.row.operation || '').toUpperCase() }}</code></template
              >
            </el-table-column>
            <el-table-column label="结果" width="88">
              <template slot-scope="scope">
                <el-tag size="small" :type="resultType(scope.row.result)">{{ resultLabel(scope.row.result) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="http_status" label="状态码" width="82" />
            <el-table-column prop="request_path" label="请求路径" min-width="210" show-overflow-tooltip />
            <el-table-column prop="ip_address" label="来源 IP" min-width="120" />
          </el-table>

          <el-empty v-else description="暂无符合条件的审计记录" />
        </section>
      </template>
    </main>
  </div>
</template>

<script>
import AppLoading from '@/components/AppLoading'
import CommonHeader from '@/components/CommonHeader'
import { exportAuditLogs, getAuditLogs, getPermissionMatrix } from '@/services/securityService'

const ROLE_META = {
  user: { label: '普通用户', short: 'U', tagType: 'success' },
  merchant: { label: '平台商户', short: 'M', tagType: 'primary' },
  admin: { label: '系统管理员', short: 'A', tagType: 'warning' },
  auditor: { label: '安全审计员', short: 'S', tagType: 'info' }
}

export default {
  name: 'SecurityCenter',
  components: { AppLoading, CommonHeader },
  data() {
    return {
      loading: true,
      exporting: false,
      loadError: '',
      roles: {},
      auditLogs: [],
      filters: { event_type: '', result: '', user_id: '' }
    }
  },
  computed: {
    roleEntries() {
      return Object.entries(this.roles).map(([key, value]) => ({
        key,
        ...(ROLE_META[key] || { label: key, short: key.slice(0, 1).toUpperCase(), tagType: 'info' }),
        description: value.description || '暂无角色说明',
        permissions: Array.isArray(value.permissions) ? value.permissions : []
      }))
    },
    permissionCount() {
      return this.roleEntries.reduce((total, role) => total + role.permissions.length, 0)
    },
    deniedCount() {
      return this.auditLogs.filter((item) => item.result !== 'success').length
    }
  },
  mounted() {
    this.loadAll()
  },
  methods: {
    async loadAll() {
      this.loading = true
      this.loadError = ''
      try {
        const [permissionResponse, auditResponse] = await Promise.all([
          getPermissionMatrix(),
          getAuditLogs({ limit: 100 })
        ])
        this.roles = permissionResponse.data?.roles || {}
        this.auditLogs = auditResponse.data?.audit_logs || []
      } catch (error) {
        this.loadError = error.response?.data?.message || '安全审计数据加载失败，请确认登录状态与后端服务'
      } finally {
        this.loading = false
      }
    },
    async loadAuditLogs() {
      this.loadError = ''
      try {
        const params = { limit: 100 }
        if (this.filters.event_type) params.event_type = this.filters.event_type
        if (this.filters.result) params.result = this.filters.result
        if (this.filters.user_id) params.user_id = this.filters.user_id
        const response = await getAuditLogs(params)
        this.auditLogs = response.data?.audit_logs || []
      } catch (error) {
        this.loadError = error.response?.data?.message || '审计记录查询失败'
      }
    },
    resetFilters() {
      this.filters = { event_type: '', result: '', user_id: '' }
      this.loadAuditLogs()
    },
    async handleExport() {
      this.exporting = true
      try {
        const response = await exportAuditLogs({ limit: 500 })
        const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: 'text/csv' })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.URL.revokeObjectURL(url)
        this.$message.success('审计日志导出成功')
      } catch (error) {
        this.$message.error(error.response?.data?.message || '审计日志导出失败')
      } finally {
        this.exporting = false
      }
    },
    formatPermission(permission) {
      return String(permission).replaceAll(':', ' · ')
    },
    roleLabel(role) {
      return ROLE_META[role]?.label || role || '未知角色'
    },
    resultType(result) {
      return { success: 'success', denied: 'warning', failure: 'danger' }[result] || 'info'
    },
    resultLabel(result) {
      return { success: '成功', denied: '拒绝', failure: '失败' }[result] || result || '未知'
    }
  }
}
</script>

<style lang="scss" scoped>
.security-page {
  min-height: 100vh;
  background: #f3f6fb;
  color: #172033;
}

.security-main {
  width: min(1440px, calc(100% - 48px));
  margin: 0 auto;
  padding: 34px 0 64px;
}

.security-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 30px;
  padding: 38px 42px;
  color: white;
  border-radius: 28px;
  background: linear-gradient(125deg, #17243a 0%, #173f4e 52%, #116466 100%);
  box-shadow: 0 24px 55px rgba(23, 50, 65, 0.2);

  h1 {
    margin: 8px 0 10px;
    font-size: 38px;
  }
  p {
    margin: 0;
    color: rgba(255, 255, 255, 0.72);
  }
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  font-weight: 700;
  color: #62dcc8;
}

.hero-badge {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 250px;
  padding: 18px 22px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);

  i {
    font-size: 28px;
    color: #62dcc8;
  }
  strong,
  span {
    display: block;
  }
  span {
    margin-top: 5px;
    color: rgba(255, 255, 255, 0.65);
    font-size: 13px;
  }
}

.page-alert {
  margin-top: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
  margin: 22px 0;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px;
  border: 1px solid #e8edf5;
  border-radius: 18px;
  background: white;

  strong,
  span {
    display: block;
  }
  strong {
    font-size: 27px;
    color: #152238;
  }
  div > span {
    margin-top: 3px;
    color: #7b879b;
    font-size: 13px;
  }
}

.stat-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  font-size: 21px;
  &.blue {
    color: #3178ed;
    background: #eaf2ff;
  }
  &.violet {
    color: #7756dc;
    background: #f0ebff;
  }
  &.green {
    color: #149778;
    background: #e5f8f2;
  }
  &.red {
    color: #d5544d;
    background: #fff0ee;
  }
}

.section-card {
  margin-top: 22px;
  padding: 30px;
  border: 1px solid #e6ebf2;
  border-radius: 22px;
  background: white;
  box-shadow: 0 12px 32px rgba(35, 50, 80, 0.06);
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 24px;

  h2 {
    margin: 6px 0;
    font-size: 25px;
  }
  p {
    margin: 0;
    color: #7b8799;
    font-size: 14px;
  }
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 18px;
}

.role-card {
  padding: 22px;
  border: 1px solid #e5eaf2;
  border-radius: 18px;
  background: linear-gradient(145deg, #fff, #f9fbfe);

  header {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  header div {
    flex: 1;
  }
  h3 {
    margin: 0;
    font-size: 17px;
  }
  header div span {
    color: #94a0b2;
    font-size: 12px;
  }
  > p {
    min-height: 42px;
    margin: 16px 0;
    color: #68758a;
    line-height: 1.6;
    font-size: 13px;
  }
}

.role-avatar {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  color: white;
  font-weight: 800;
  background: #355b81;
}
.role-user .role-avatar {
  background: #1b9d79;
}
.role-merchant .role-avatar {
  background: #3477db;
}
.role-admin .role-avatar {
  background: #d77a31;
}
.role-auditor .role-avatar {
  background: #7254bd;
}

.permission-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  span {
    padding: 7px 10px;
    color: #46556d;
    border-radius: 9px;
    background: #f0f4f9;
    font-size: 12px;
  }
  i {
    margin-right: 5px;
    color: #1b9d79;
  }
}

.filter-bar {
  display: grid;
  grid-template-columns: 1.5fr 1fr 0.8fr auto auto;
  gap: 10px;
  margin-bottom: 20px;
}

.audit-table {
  width: 100%;
}
.operator-cell {
  strong,
  span {
    display: block;
  }
  span {
    margin-top: 3px;
    color: #8a96a8;
    font-size: 12px;
  }
}
code {
  padding: 4px 7px;
  color: #355b81;
  border-radius: 6px;
  background: #edf3fa;
  font-size: 11px;
}

@media (max-width: 1000px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .role-grid {
    grid-template-columns: 1fr;
  }
  .filter-bar {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 680px) {
  .security-main {
    width: min(100% - 24px, 1440px);
    padding-top: 16px;
  }
  .security-hero {
    align-items: flex-start;
    flex-direction: column;
    padding: 28px 24px;
  }
  .security-hero h1 {
    font-size: 29px;
  }
  .hero-badge {
    min-width: 0;
    width: 100%;
    box-sizing: border-box;
  }
  .stats-grid,
  .filter-bar {
    grid-template-columns: 1fr;
  }
  .section-card {
    padding: 20px 16px;
  }
  .section-heading {
    flex-direction: column;
  }
}
</style>
