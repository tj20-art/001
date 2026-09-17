<template>
  <div class="page-shell login-page">
    <div class="login-layout">
      <section class="marketing-panel">
        <div class="eyebrow">FreeSpace Mall</div>
        <h1>多重身份校验，安心进入你的数字商城</h1>
        <p>密码与用户证书共同验证身份。管理员和审计员还需要认证器动态验证码，每一次关键访问都有迹可循。</p>
        <div class="feature-list">
          <div class="feature-item">
            <i class="el-icon-lock"></i>
            <span>密码与证书双重校验</span>
          </div>
          <div class="feature-item">
            <i class="el-icon-goods"></i>
            <span>国密安全信封保护敏感请求</span>
          </div>
          <div class="feature-item">
            <i class="el-icon-user-solid"></i>
            <span>角色最小权限与审计追踪</span>
          </div>
        </div>
      </section>

      <section class="login-card">
        <div class="card-head">
          <h2>欢迎回来</h2>
          <p>输入登录密码，并选择注册后下载的用户证书</p>
        </div>

        <el-input
          v-model="password"
          show-password
          autocomplete="current-password"
          prefix-icon="el-icon-lock"
          placeholder="请输入登录密码"
          @keyup.enter.native="handleCertLogin"
        />

        <div class="upload-panel" @click="triggerFile">
          <div class="upload-icon"><i class="el-icon-upload2"></i></div>
          <div class="upload-main">{{ certFileName || '点击上传证书文件' }}</div>
          <div class="upload-sub">仅支持 PEM / CRT / CER 文件</div>
        </div>
        <input ref="fileInput" type="file" accept=".pem,.crt,.cer" class="hidden-input" @change="handleCertSelect" />

        <el-alert
          title="提示"
          type="info"
          :closable="false"
          show-icon
          description="如果你刚完成注册，请先保存自动下载的证书，再使用该证书登录。"
        />

        <el-button type="primary" class="action-btn" @click="handleCertLogin" :loading="loading" :disabled="!certFile">
          安全登录
        </el-button>

        <div class="footer-line">
          还没有账号？
          <router-link to="/user-register">立即注册并领取证书</router-link>
        </div>
      </section>
    </div>

    <el-dialog
      :title="mfaSetupRequired ? '绑定认证器' : '双因素认证'"
      :visible.sync="mfaVisible"
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
            <template slot="prepend">URI</template>
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
          prefix-icon="el-icon-key"
          @keyup.enter.native="submitMfa"
        />
      </div>
      <span slot="footer">
        <el-button @click="mfaVisible = false">取消</el-button>
        <el-button type="primary" :loading="mfaLoading" @click="submitMfa">
          {{ mfaSetupRequired ? '绑定并登录' : '验证并登录' }}
        </el-button>
      </span>
    </el-dialog>

    <el-dialog title="请保存恢复码" :visible.sync="recoveryVisible" width="500px" :show-close="false">
      <div class="recovery-dialog">
        <el-alert title="每个恢复码只能使用一次，关闭后系统不会再次明文显示" type="warning" :closable="false" />
        <div class="recovery-grid">
          <code v-for="code in recoveryCodes" :key="code">{{ code }}</code>
        </div>
      </div>
      <span slot="footer">
        <el-button @click="copyRecoveryCodes">复制恢复码</el-button>
        <el-button type="primary" @click="finishRecovery">我已安全保存</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import { mapActions } from 'vuex'

export default {
  name: 'UserLogin',
  data() {
    return {
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
      this.$router.push(`/profile/${userId}`)
    }
  }
}
</script>

<style scoped lang="scss">
.login-page {
  padding: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-layout {
  width: 100%;
  max-width: 1180px;
  display: grid;
  grid-template-columns: 1.2fr 0.95fr;
  gap: 28px;
  align-items: stretch;
}

.marketing-panel {
  padding: 44px;
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.96), rgba(87, 61, 255, 0.92));
  color: #fff;
  box-shadow: 0 24px 60px rgba(64, 158, 255, 0.28);

  .eyebrow {
    display: inline-block;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.16);
    margin-bottom: 22px;
    font-size: 13px;
  }

  h1 {
    font-size: 38px;
    line-height: 1.25;
    margin: 0 0 16px;
  }

  p {
    font-size: 16px;
    line-height: 1.8;
    color: rgba(255, 255, 255, 0.88);
    max-width: 520px;
  }
}

.feature-list {
  margin-top: 28px;
  display: grid;
  gap: 16px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);

  i {
    font-size: 18px;
  }
}

.login-card {
  padding: 32px;
  background: #fff;
  border-radius: 28px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.1);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-head {
  text-align: left;

  h2 {
    margin: 0 0 8px;
    font-size: 28px;
    color: #111827;
  }

  p {
    margin: 0;
    color: #6b7280;
    line-height: 1.7;
  }
}

.upload-panel {
  border: 1.5px dashed #cbd5e1;
  border-radius: 22px;
  padding: 28px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  background: linear-gradient(180deg, #f8fbff, #ffffff);

  &:hover {
    border-color: #409eff;
    transform: translateY(-1px);
    box-shadow: 0 12px 24px rgba(64, 158, 255, 0.12);
  }
}

.upload-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(64, 158, 255, 0.12);
  color: #409eff;
  font-size: 24px;
}

.upload-main {
  color: #111827;
  font-weight: 600;
  margin-bottom: 6px;
  word-break: break-all;
}

.upload-sub {
  color: #6b7280;
  font-size: 13px;
}

.hidden-input {
  display: none;
}

.action-btn {
  width: 100%;
  height: 48px;
  border-radius: 14px;
  font-size: 16px;
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

@media screen and (max-width: 960px) {
  .login-page {
    padding: 18px;
  }

  .login-layout {
    grid-template-columns: 1fr;
  }

  .marketing-panel,
  .login-card {
    padding: 24px;
  }

  .marketing-panel h1 {
    font-size: 30px;
  }
}
</style>
