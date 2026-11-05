<template>
  <div class="page-shell not-found-page">
    <div class="not-found-card section-card">
      <div class="code">404</div>
      <h1>页面不存在</h1>
      <p>抱歉，你访问的页面可能已经被移动、删除，或者链接地址有误。</p>
      <div class="actions">
        <el-button type="primary" round @click="$router.push('/home')">返回商城首页</el-button>
        <el-button round @click="$router.push('/user-login')">返回登录页</el-button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'PageNotFound'
}
</script>

<style scoped lang="scss">
.not-found-page {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.not-found-card {
  max-width: 520px;
  width: 100%;
  padding: 48px 32px;
  text-align: center;
}

.code {
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  color: #409eff;
  margin-bottom: 12px;
}

h1 {
  margin: 0 0 12px;
  color: #111827;
}

p {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

.actions {
  margin-top: 24px;
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
