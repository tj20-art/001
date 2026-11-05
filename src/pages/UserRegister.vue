<template>
  <div class="page-shell register-page">
    <div class="register-layout">
      <section class="intro-panel">
        <div class="eyebrow">新用户注册</div>
        <h1>创建会员账号，注册成功后立即领取证书</h1>
        <p>系统会在注册成功后自动签发并下载你的用户证书。请妥善保存该证书，它将用于后续登录。</p>
        <ul class="tips">
          <li>用户名：5-20位字母、数字或下划线</li>
          <li>密码：需包含大小写字母、数字与特殊符号</li>
          <li>手机号：必须为11位大陆手机号</li>
        </ul>
      </section>

      <section class="register-card">
        <div class="card-head">
          <h2>创建账户</h2>
          <p>注册完成后会弹出证书下载提示窗口，并自动开始下载。</p>
        </div>

        <el-form ref="registerForm" :model="formData" :rules="rules" label-position="top">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="formData.username" placeholder="请输入用户名" @input="handleInput('username', $event)" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="formData.password"
              show-password
              placeholder="请输入密码"
              @input="handleInput('password', $event)"
            />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input v-model="formData.confirmPassword" show-password placeholder="请再次输入密码" />
          </el-form-item>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="formData.phone" placeholder="请输入手机号" @input="handleInput('phone', $event)" />
          </el-form-item>

          <el-button type="primary" class="submit-btn" :loading="loading" @click="handleRegister">
            注册并下载证书
          </el-button>
        </el-form>

        <div class="footer-line">
          已有账号？
          <router-link to="/user-login">立即登录</router-link>
        </div>
      </section>
    </div>

    <el-dialog
      title="注册成功"
      :visible.sync="showCertDialog"
      width="460px"
      :close-on-click-modal="false"
      :show-close="false"
    >
      <div class="cert-dialog">
        <i class="el-icon-success success-icon"></i>
        <h3>用户注册成功，证书已准备完成</h3>
        <p>系统已经为你生成用户证书，并且已尝试自动下载。请把证书保存到安全位置，后续登录时需要上传它。</p>
        <el-alert
          title="重要提醒"
          type="warning"
          :closable="false"
          description="证书文件一旦丢失，将无法直接进行证书登录。"
        />
      </div>
      <span slot="footer" class="dialog-footer">
        <el-button @click="downloadCertificate">重新下载证书</el-button>
        <el-button type="primary" @click="goToLogin">前往登录</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import { register, downloadCertificateByDeliveryToken } from '@/services/userService'
import { validateField, sanitizeInput } from '@/utils/security'

export default {
  name: 'UserRegister',
  data() {
    const validateByType = (type) => (rule, value, callback) => {
      const result = validateField(value, type)
      if (!result.valid) {
        callback(new Error(result.msg))
        return
      }
      callback()
    }

    const validateConfirmPassword = (rule, value, callback) => {
      if (value !== this.formData.password) {
        callback(new Error('两次输入的密码不一致'))
        return
      }
      callback()
    }

    return {
      formData: {
        username: '',
        password: '',
        confirmPassword: '',
        phone: ''
      },
      loading: false,
      showCertDialog: false,
      certBlob: null,
      certFileName: 'user_certificate.crt',
      downloadToken: '',
      rules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' },
          { validator: validateByType('username'), trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' },
          { validator: validateByType('password'), trigger: 'blur' }
        ],
        confirmPassword: [
          { required: true, message: '请确认密码', trigger: 'blur' },
          { validator: validateConfirmPassword, trigger: 'blur' }
        ],
        phone: [
          { required: true, message: '请输入手机号', trigger: 'blur' },
          { validator: validateByType('phone'), trigger: 'blur' }
        ]
      }
    }
  },
  methods: {
    handleInput(field, value) {
      this.formData[field] = sanitizeInput(value)
    },
    parseFilename(headers = {}) {
      const disposition = headers['content-disposition'] || headers['Content-Disposition'] || ''
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
      if (utf8Match && utf8Match[1]) {
        return decodeURIComponent(utf8Match[1])
      }
      const normalMatch = disposition.match(/filename="?([^";]+)"?/i)
      if (normalMatch && normalMatch[1]) {
        return decodeURIComponent(normalMatch[1])
      }
      return `${this.formData.username || 'user'}_certificate.crt`
    },
    createBlobFromPem(pemText, contentType = 'application/x-pem-file') {
      return new Blob([pemText], { type: `${contentType};charset=utf-8` })
    },
    createBlobFromBase64(base64Text, contentType = 'application/x-pem-file') {
      const binary = window.atob(base64Text)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i)
      }
      return new Blob([bytes], { type: contentType })
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
    async downloadCertificate() {
      if (this.certBlob) {
        this.saveBlob(this.certBlob, this.certFileName)
        return
      }

      if (!this.downloadToken) {
        this.$message.warning('当前没有可重新下载的证书，请重新注册或联系管理员')
        return
      }

      try {
        const response = await downloadCertificateByDeliveryToken(this.downloadToken)
        const blob =
          response.data instanceof Blob
            ? response.data
            : new Blob([response.data], { type: response.headers?.['content-type'] || 'application/x-pem-file' })
        this.certFileName = this.parseFilename(response.headers || {})
        this.certBlob = blob
        this.saveBlob(blob, this.certFileName)
      } catch (error) {
        // 统一错误拦截器已经向用户展示失败原因
      }
    },
    async handleJsonRegisterSuccess(response) {
      const payload = response && response.data ? response.data : {}
      const certificate = payload.certificate || {}
      const delivery = payload.certificate_delivery || {}

      this.certFileName = certificate.filename || `${this.formData.username}_certificate.crt`
      this.downloadToken = delivery.download_token || ''

      if (certificate.pem) {
        this.certBlob = this.createBlobFromPem(certificate.pem, certificate.content_type)
      } else if (certificate.base64) {
        this.certBlob = this.createBlobFromBase64(certificate.base64, certificate.content_type)
      } else if (delivery.download_token) {
        await this.downloadCertificate()
      } else {
        throw new Error('注册成功，但响应中未找到证书内容')
      }

      if (this.certBlob) {
        this.saveBlob(this.certBlob, this.certFileName)
      }

      this.showCertDialog = true
      this.$notify({
        title: '注册成功',
        message: '证书已开始下载，请妥善保存。',
        type: 'success',
        duration: 3200
      })
    },
    async handleRegister() {
      this.$refs.registerForm.validate(async (valid) => {
        if (!valid) return

        this.loading = true
        try {
          const response = await register({
            username: this.formData.username,
            password: this.formData.password,
            phone: this.formData.phone
          })

          const isLegacyFileResponse = response && response.headers && (response.data instanceof Blob || response.data)
          if (isLegacyFileResponse && !response.code) {
            this.certBlob =
              response.data instanceof Blob
                ? response.data
                : new Blob([response.data], {
                    type: response.headers['content-type'] || 'application/x-pem-file'
                  })
            this.certFileName = this.parseFilename(response.headers || {})
            this.saveBlob(this.certBlob, this.certFileName)
            this.showCertDialog = true
            this.$notify({
              title: '注册成功',
              message: '证书已开始下载，请妥善保存。',
              type: 'success',
              duration: 3200
            })
            return
          }

          await this.handleJsonRegisterSuccess(response)
        } catch (error) {
          // 统一错误拦截器已经向用户展示失败原因
        } finally {
          this.loading = false
        }
      })
    },
    goToLogin() {
      this.showCertDialog = false
      this.$router.push('/user-login')
    }
  }
}
</script>

<style scoped lang="scss">
.register-page {
  padding: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.register-layout {
  width: 100%;
  max-width: 1180px;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 28px;
}

.intro-panel {
  padding: 44px;
  border-radius: 28px;
  background: linear-gradient(160deg, #101828, #243b53);
  color: #fff;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);

  .eyebrow {
    display: inline-block;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    margin-bottom: 22px;
    font-size: 13px;
  }

  h1 {
    margin: 0 0 16px;
    font-size: 36px;
    line-height: 1.28;
  }

  p {
    color: rgba(255, 255, 255, 0.82);
    font-size: 16px;
    line-height: 1.8;
  }
}

.tips {
  margin: 28px 0 0;
  padding-left: 18px;
  color: rgba(255, 255, 255, 0.88);
  line-height: 2;
}

.register-card {
  background: #fff;
  border-radius: 28px;
  padding: 32px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.1);
}

.card-head {
  margin-bottom: 16px;

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

.submit-btn {
  width: 100%;
  height: 48px;
  margin-top: 8px;
  border-radius: 14px;
  font-size: 16px;
}

.footer-line {
  text-align: center;
  color: #6b7280;
  margin-top: 18px;

  a {
    color: #409eff;
    margin-left: 4px;
  }
}

.cert-dialog {
  text-align: center;

  .success-icon {
    font-size: 56px;
    color: #67c23a;
    margin-bottom: 10px;
  }

  h3 {
    margin: 8px 0 14px;
    color: #111827;
  }

  p {
    color: #4b5563;
    line-height: 1.8;
    margin-bottom: 18px;
  }
}

@media screen and (max-width: 960px) {
  .register-page {
    padding: 18px;
  }

  .register-layout {
    grid-template-columns: 1fr;
  }

  .intro-panel,
  .register-card {
    padding: 24px;
  }

  .intro-panel h1 {
    font-size: 30px;
  }
}
</style>
