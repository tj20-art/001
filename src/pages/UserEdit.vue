<template>
  <el-dialog title="修改个人信息" :visible="visible" width="400px" :close-on-click-modal="false">
    <el-form ref="form" :model="formData" label-width="100px">
      <el-form-item label="旧密码" prop="old_password" :rules="[{ required: true, message: '请输入旧密码' }]">
        <el-input v-model="formData.old_password" type="password"></el-input>
      </el-form-item>

      <el-form-item label="手机号" prop="phone" :rules="[{ required: true, message: '请输入手机号' }]">
        <el-input v-model="formData.phone" disabled></el-input>
      </el-form-item>

      <el-form-item label="新用户名" prop="new_username">
        <el-input v-model="formData.new_username" placeholder="不修改请留空"></el-input>
        <div slot="help">5-20位字母、数字、下划线</div>
      </el-form-item>

      <el-form-item label="新密码" prop="new_password">
        <el-input v-model="formData.new_password" type="password" placeholder="不修改请留空"></el-input>
        <div slot="help">需包含大小写字母、数字、特殊符号，8-20位</div>
      </el-form-item>
    </el-form>

    <div slot="footer">
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit">确定</el-button>
    </div>
  </el-dialog>
</template>

<script>
import { mapActions, mapMutations } from 'vuex'
import { validateField } from '@/utils/security'

const createDefaultForm = () => ({
  old_password: '',
  phone: '',
  new_username: '',
  new_password: ''
})

export default {
  name: 'UserEdit',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    userInfo: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      formData: createDefaultForm()
    }
  },
  watch: {
    userInfo: {
      immediate: true,
      handler(newVal) {
        this.formData = {
          ...createDefaultForm(),
          phone: newVal && newVal.phone ? newVal.phone : ''
        }
      }
    },
    visible(val) {
      if (val) {
        this.formData = {
          ...createDefaultForm(),
          phone: this.userInfo && this.userInfo.phone ? this.userInfo.phone : ''
        }
      }
    }
  },
  methods: {
    ...mapActions('userModule', ['updateUserInfo']),
    ...mapMutations('authModule', ['MERGE_USER']),
    handleCancel() {
      this.$emit('update:visible', false)
    },
    async handleSubmit() {
      if (!this.formData.old_password) {
        this.$message.error('请输入旧密码')
        return
      }

      if (this.formData.new_username && !validateField(this.formData.new_username, 'username').valid) {
        this.$message.error('用户名格式错误')
        return
      }

      if (this.formData.new_password && !validateField(this.formData.new_password, 'password').valid) {
        this.$message.error('密码格式错误')
        return
      }

      const userData = { ...this.formData }
      if (!userData.new_username) delete userData.new_username
      if (!userData.new_password) delete userData.new_password

      try {
        await this.updateUserInfo({
          userId: this.userInfo.id,
          userData
        })

        if (userData.new_username) {
          this.MERGE_USER({ username: userData.new_username })
        }

        this.$message.success('信息更新成功')
        this.$emit('update:visible', false)
        this.$emit('refresh-user-info')
      } catch (error) {
        this.$message.error(error.response?.data?.message || '更新失败')
      }
    }
  }
}
</script>
