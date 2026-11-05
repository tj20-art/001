<template>
  <div class="page-shell profile-page">
    <common-header />

    <main class="profile-main page-main">
      <app-loading v-if="loading" />

      <el-alert v-else-if="error" title="个人信息加载失败" type="error" :closable="false" show-icon />

      <template v-else-if="userDetail">
        <section class="profile-hero section-card">
          <div class="avatar-box">{{ userDetail.username.slice(0, 1).toUpperCase() }}</div>
          <div class="hero-text">
            <span class="hero-tag">{{ roleCenterLabel }}</span>
            <h1>{{ userDetail.username }}</h1>
            <p>欢迎回来，这里可以查看个人资料、修改信息、重新下载证书，并快速进入商品、购物车与订单页面。</p>
          </div>
          <div class="hero-actions">
            <el-button type="primary" round icon="el-icon-house" @click="$router.push('/home')">进入商城</el-button>
            <el-button round icon="el-icon-download" :loading="downloadingCert" @click="handleDownloadCertificate"
              >下载证书</el-button
            >
            <el-button round @click="showEditDialog = true">编辑资料</el-button>
          </div>
        </section>

        <section class="profile-grid">
          <div class="detail-card section-card">
            <h2>账号信息</h2>
            <div class="detail-row">
              <span>用户ID</span><strong>{{ userDetail.id }}</strong>
            </div>
            <div class="detail-row">
              <span>用户名</span><strong>{{ userDetail.username }}</strong>
            </div>
            <div class="detail-row">
              <span>手机号</span><strong>{{ userDetail.phone }}</strong>
            </div>
            <div class="detail-row">
              <span>角色</span>
              <el-tag :type="roleTagType">
                {{ roleLabel }}
              </el-tag>
            </div>
            <div class="detail-row">
              <span>创建时间</span><strong>{{ formatTime(userDetail.created_at) }}</strong>
            </div>
          </div>

          <div class="detail-card section-card">
            <h2>快捷入口</h2>
            <div class="action-list">
              <button class="action-item" @click="$router.push('/home')">
                <i class="el-icon-goods"></i>
                <div>
                  <strong>浏览商品</strong>
                  <span>查看所有在售商品</span>
                </div>
              </button>
              <button v-if="canManageProducts" class="action-item" @click="$router.push('/my-products')">
                <i class="el-icon-s-shop"></i>
                <div>
                  <strong>我的商品</strong>
                  <span>发布、编辑和下架自己的商品</span>
                </div>
              </button>
              <button v-if="canShop" class="action-item" @click="$router.push('/cart')">
                <i class="el-icon-shopping-cart-2"></i>
                <div>
                  <strong>购物车</strong>
                  <span>管理已选商品并提交订单</span>
                </div>
              </button>
              <button v-if="canShop" class="action-item" @click="$router.push('/orders')">
                <i class="el-icon-tickets"></i>
                <div>
                  <strong>我的订单</strong>
                  <span>查看订单状态与明细</span>
                </div>
              </button>
              <button class="action-item" @click="handleDownloadCertificate">
                <i class="el-icon-download"></i>
                <div>
                  <strong>下载证书</strong>
                  <span>重新保存当前账号证书</span>
                </div>
              </button>
              <button class="action-item" @click="showEditDialog = true">
                <i class="el-icon-edit-outline"></i>
                <div>
                  <strong>编辑资料</strong>
                  <span>修改用户名或密码</span>
                </div>
              </button>
              <button v-if="isAdmin" class="action-item" @click="$router.push('/user-list')">
                <i class="el-icon-user-solid"></i>
                <div>
                  <strong>用户管理</strong>
                  <span>查看平台用户列表</span>
                </div>
              </button>
              <button v-if="isAdmin || isAuditor" class="action-item" @click="$router.push('/security-center')">
                <i class="el-icon-view"></i>
                <div>
                  <strong>安全审计</strong>
                  <span>查看权限矩阵和审计事件</span>
                </div>
              </button>
            </div>
          </div>
        </section>
      </template>
    </main>

    <user-edit
      :visible="showEditDialog"
      :user-info="userDetail || {}"
      @refresh-user-info="fetchUserInfo"
      @update:visible="showEditDialog = $event"
    />
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapState, mapGetters } from 'vuex'
import UserEdit from './UserEdit.vue'
import { downloadUserCertificate } from '@/services/userService'

export default {
  name: 'UserProfile',
  components: { CommonHeader, AppLoading, UserEdit },
  data() {
    return {
      loading: true,
      error: false,
      showEditDialog: false,
      downloadingCert: false
    }
  },
  computed: {
    ...mapState('userModule', ['userDetail']),
    ...mapGetters('authModule', ['isAdmin', 'isAuditor', 'canManageProducts', 'canShop']),
    roleLabel() {
      return (
        { user: '普通用户', merchant: '商户', admin: '管理员', auditor: '审计员' }[this.userDetail.role] || '未知角色'
      )
    },
    roleCenterLabel() {
      return (
        { user: '会员中心', merchant: '商户中心', admin: '管理中心', auditor: '审计中心' }[this.userDetail.role] ||
        '个人中心'
      )
    },
    roleTagType() {
      return { user: 'success', merchant: 'primary', admin: 'warning', auditor: 'info' }[this.userDetail.role] || 'info'
    }
  },
  mounted() {
    this.fetchUserInfo()
  },
  methods: {
    ...mapActions('userModule', ['getUserInfo']),
    parseFilename(headers = {}) {
      const disposition = headers['content-disposition'] || headers['Content-Disposition'] || ''
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
      if (utf8Match && utf8Match[1]) return decodeURIComponent(utf8Match[1])
      const normalMatch = disposition.match(/filename="?([^";]+)"?/i)
      if (normalMatch && normalMatch[1]) return decodeURIComponent(normalMatch[1])
      return `${(this.userDetail && this.userDetail.username) || 'user'}_certificate.crt`
    },
    saveBlob(blob, filename) {
      const blobUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(blobUrl)
    },
    async handleDownloadCertificate() {
      if (!this.userDetail || !this.userDetail.id) {
        this.$message.error('当前用户信息不存在，无法下载证书')
        return
      }

      this.downloadingCert = true
      try {
        const response = await downloadUserCertificate(this.userDetail.id)
        const blob =
          response.data instanceof Blob
            ? response.data
            : new Blob([response.data], {
                type: (response.headers && response.headers['content-type']) || 'application/x-pem-file'
              })
        this.saveBlob(blob, this.parseFilename(response.headers || {}))
        this.$message.success('证书下载成功')
      } finally {
        this.downloadingCert = false
      }
    },
    async fetchUserInfo() {
      this.loading = true
      this.error = false
      try {
        const userId = this.$route.params.user_id
        if (!userId || isNaN(userId)) {
          this.error = true
          return
        }
        await this.getUserInfo(userId)
      } catch (error) {
        this.error = true
      } finally {
        this.loading = false
      }
    },
    formatTime(timeStr) {
      if (!timeStr) return '--'
      return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped lang="scss">
.profile-hero,
.detail-card {
  padding: 24px;
}

.profile-hero {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 20px;
  align-items: center;
  margin-bottom: 20px;
}

.avatar-box {
  width: 86px;
  height: 86px;
  border-radius: 28px;
  background: linear-gradient(135deg, #409eff, #7c4dff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 34px;
  font-weight: 700;
}

.hero-text h1 {
  margin: 10px 0;
  font-size: 30px;
  color: #111827;
}

.hero-text p {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

.hero-tag {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 999px;
  background: #eef6ff;
  color: #409eff;
  font-size: 12px;
  font-weight: 600;
}

.hero-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.profile-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.detail-card h2 {
  margin: 0 0 18px;
  font-size: 22px;
  color: #111827;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 0;
  border-bottom: 1px solid #edf2f7;
  gap: 12px;
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row span {
  color: #6b7280;
}

.detail-row strong {
  color: #111827;
  font-weight: 600;
  text-align: right;
}

.action-list {
  display: grid;
  gap: 14px;
}

.action-item {
  border: none;
  border-radius: 20px;
  padding: 18px;
  display: flex;
  gap: 14px;
  align-items: center;
  background: linear-gradient(180deg, #f8fbff, #ffffff);
  cursor: pointer;
  text-align: left;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.action-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 28px rgba(64, 158, 255, 0.14);
}

.action-item i {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(64, 158, 255, 0.12);
  color: #409eff;
  font-size: 20px;
}

.action-item strong {
  display: block;
  color: #111827;
  margin-bottom: 4px;
}

.action-item span {
  color: #6b7280;
  font-size: 13px;
}

@media screen and (max-width: 980px) {
  .profile-hero {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .avatar-box {
    margin: 0 auto;
  }

  .hero-actions {
    width: 100%;
  }

  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
