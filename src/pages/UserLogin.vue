<template>
  <div class="page-shell login-page">
    <div class="login-layout">
      <section class="login-cover" aria-label="FreeSpace Mall">
        <img :src="heroImage" alt="" width="1536" height="1024" />
        <div><RouterLink to="/home">FreeSpace Mall</RouterLink></div>
      </section>
      <form class="login-card section-card" @submit.prevent="handleCertLogin">
        <div class="card-head">
          <RouterLink class="back-home" to="/home">返回商城</RouterLink>
          <h1>登录商城</h1>
          <p>使用注册时保存的证书和密码验证身份。</p>
        </div>
        <label class="field-label" for="login-password">密码</label>
        <el-input
          id="login-password"
          v-model="password"
          type="password"
          show-password
          autocomplete="current-password"
          placeholder="输入密码"
        />

        <label class="field-label" for="login-certificate-button">登录证书</label>
        <button id="login-certificate-button" type="button" class="upload-panel" @click="triggerFile">
          <el-icon class="upload-icon" aria-hidden="true"><Upload /></el-icon>
          <span class="upload-main">{{ certFileName || '选择证书文件' }}</span>
          <span v-if="certFileName" class="upload-sub">更换</span>
        </button>
        <input ref="fileInput" type="file" accept=".pem,.crt,.cer" class="hidden-input" @change="handleCertSelect" />
        <p class="file-hint">支持 PEM、CRT 和 CER。</p>

        <el-button type="primary" native-type="submit" class="action-btn" :loading="loading">安全登录</el-button>
        <p class="footer-line">还没有账号？<RouterLink to="/user-register">注册并领取证书</RouterLink></p>
      </form>
    </div>

    <el-dialog
      :title="mfaSetupRequired ? '绑定认证器' : '双因素认证'"
      v-model="mfaVisible"
      width="520px"
      :close-on-click-modal="false"
    >
      <div class="mfa-dialog">
        <template v-if="mfaSetupRequired">
          <div class="step-label">首次登录设置</div>
          <p>在 Google Authenticator、Microsoft Authenticator 等应用中添加密钥，然后输入当前 6 位验证码完成绑定。</p>
          <div class="secret-box">
            <span>认证器密钥</span>
            <strong>{{ totpSecret }}</strong>
          </div>
          <el-input v-model="otpauthUri" readonly>
            <template #prepend>URI</template>
          </el-input>
        </template>
        <template v-else>
          <p>请输入认证器生成的 6 位动态验证码。设备不可用时，也可以输入尚未使用的一次性恢复码。</p>
        </template>
        <el-input
          v-model="mfaCode"
          maxlength="16"
          autocomplete="one-time-code"
          placeholder="6 位验证码或恢复码"
          prefix-icon="Key"
          @keyup.enter="submitMfa"
        />
      </div>
      <template #footer>
        <el-button @click="mfaVisible = false">取消</el-button>
        <el-button type="primary" :loading="mfaLoading" @click="submitMfa">
          {{ mfaSetupRequired ? '绑定并登录' : '验证并登录' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog title="请保存恢复码" v-model="recoveryVisible" width="500px" :show-close="false">
      <div class="recovery-dialog">
        <el-alert title="每个恢复码只能使用一次，关闭后系统不会再次明文显示" type="warning" :closable="false" />
        <div class="recovery-grid">
          <code v-for="code in recoveryCodes" :key="code">{{ code }}</code>
        </div>
      </div>
      <template #footer>
        <el-button @click="copyRecoveryCodes">复制恢复码</el-button>
        <el-button type="primary" @click="finishRecovery">我已安全保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { mapActions } from 'vuex'
import heroImage from '@/assets/storefront-homewares.jpg'

export default {
  name: 'UserLogin',
  data() {
    return {
      heroImage,
      certFile: null,
      certFileName: '',
      password: '',
      loading: false,
      mfaVisible: false,
      mfaLoading: false,
      mfaSetupRequired: false,
      mfaToken: '',
      mfaCode: '',
      totpSecret: '',
      otpauthUri: '',
      recoveryVisible: false,
      recoveryCodes: []
    }
  },
  methods: {
    ...mapActions('authModule', ['loginByCert', 'completeMfa']),
    triggerFile() {
      this.$refs.fileInput.click()
    },
    handleCertSelect(event) {
      const file = event.target.files[0]
      if (!file) return
      this.certFile = file
      this.certFileName = file.name
    },
    async handleCertLogin() {
      if (this.loading) return
      if (!this.certFile) {
        this.$message.warning('请先选择证书文件')
        return
      }
      if (!this.password) {
        this.$message.warning('请输入登录密码')
        return
      }
      this.loading = true
      try {
        const response = await this.loginByCert({ certFile: this.certFile, password: this.password })
        if (response?.data?.mfa_required) {
          this.mfaSetupRequired = !!response.data.mfa_setup_required
          this.mfaToken = response.data.mfa_token
          this.totpSecret = response.data.totp_secret || ''
          this.otpauthUri = response.data.otpauth_uri || ''
          this.mfaCode = ''
          this.mfaVisible = true
          return
        }
        this.finishLogin()
      } catch (error) {
        // 统一错误拦截器已经向用户展示失败原因
      } finally {
        this.loading = false
      }
    },
    async submitMfa() {
      if (this.mfaLoading) return
      if (!this.mfaCode.trim()) {
        this.$message.warning('请输入动态验证码或恢复码')
        return
      }
      this.mfaLoading = true
      try {
        const response = await this.completeMfa({
          mfaToken: this.mfaToken,
          code: this.mfaCode.trim(),
          setupRequired: this.mfaSetupRequired
        })
        this.mfaVisible = false
        this.recoveryCodes = response?.data?.recovery_codes || []
        if (this.recoveryCodes.length) {
          this.recoveryVisible = true
        } else {
          this.finishLogin()
        }
      } catch {
        // The API client displays MFA errors.
      } finally {
        this.mfaLoading = false
      }
    },
    async copyRecoveryCodes() {
      await navigator.clipboard.writeText(this.recoveryCodes.join('\n'))
      this.$message.success('恢复码已复制')
    },
    finishRecovery() {
      this.recoveryVisible = false
      this.finishLogin()
    },
    finishLogin() {
      const userId = this.$store.getters['authModule/userId']
      this.$message.success('身份验证通过，欢迎回来')
      const redirect = this.$route.query.redirect
      const internal = typeof redirect === 'string' && /^\/(?!\/)/.test(redirect) && !redirect.includes('\\')
      const target = internal && this.$router.resolve(redirect)
      const destination =
        target && (target.meta.requiresAuth || target.meta.restoreAuth) ? target.fullPath : '/profile/' + userId
      this.$router.replace(destination).catch(() => {})
    }
  }
}
</script>

<style scoped lang="scss">
.login-page {
  display: grid;
  place-items: center;
  padding: 24px;
}
.login-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 18px;
  width: min(960px, 100%);
}
.login-cover {
  position: relative;
  min-height: 460px;
  border-radius: var(--mall-radius);
  overflow: hidden;
}
.login-cover img {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
  object-fit: cover;
}
.login-cover div {
  position: absolute;
  inset: 0 0 auto;
  padding: 20px;
  background: linear-gradient(180deg, rgb(28 22 16 / 65%), transparent);
  color: white;
  font-weight: 700;
}
.login-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: clamp(18px, 4vw, 36px);
}
.card-head h1 {
  margin: 12px 0 6px;
  font-size: 34px;
  letter-spacing: -0.04em;
}
.card-head p,
.file-hint {
  color: var(--mall-muted);
  font-size: 13px;
  line-height: 1.5;
}
.card-head p {
  margin: 0 0 18px;
}
.back-home,
.footer-line a {
  color: var(--mall-accent);
  font-weight: 600;
  font-size: 14px;
}
.field-label {
  margin-bottom: 7px;
  font-size: 14px;
  font-weight: 600;
}
.login-card > .el-input {
  margin-bottom: 14px;
}
.upload-panel {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 46px;
  width: 100%;
  padding: 8px 10px;
  border: 1px dashed #b9a99c;
  border-radius: 8px;
  background: #faf8f4;
  color: var(--mall-ink);
  cursor: pointer;
  text-align: left;
}
.upload-icon {
  flex: none;
  color: var(--mall-accent);
  font-size: 18px;
}
.upload-main {
  min-width: 0;
  overflow-wrap: anywhere;
  flex: 1;
  font-size: 14px;
}
.upload-sub {
  color: var(--mall-accent);
  font-size: 13px;
}
.hidden-input {
  display: none;
}
.file-hint {
  margin: 6px 0 16px;
}
.action-btn {
  min-height: 44px;
  width: 100%;
}
.footer-line {
  margin: 16px 0 0;
  font-size: 14px;
}
@media (max-width: 700px) {
  .login-page {
    padding: 16px;
    min-height: 100vh;
    min-height: 100dvh;
  }
  .login-layout {
    display: block;
    max-width: 460px;
  }
  .login-cover {
    display: none;
  }
  .card-head h1 {
    font-size: 28px;
  }
}

.mfa-dialog,
.recovery-dialog {
  display: grid;
  gap: 18px;
  color: #475569;
  line-height: 1.7;
}

.step-label {
  color: #2563eb;
  font-weight: 700;
  font-size: 13px;
}

.secret-box {
  padding: 16px;
  border-radius: 14px;
  background: #f1f5f9;
  display: grid;
  gap: 5px;

  span {
    color: #64748b;
    font-size: 12px;
  }

  strong {
    color: #0f172a;
    letter-spacing: 2px;
    word-break: break-all;
  }
}

.recovery-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;

  code {
    padding: 10px 12px;
    border-radius: 10px;
    background: #0f172a;
    color: #f8fafc;
    text-align: center;
  }
}

.footer-line {
  text-align: center;
  color: #6b7280;
  font-size: 14px;

  a {
    color: #409eff;
    margin-left: 4px;
  }
}
</style>
