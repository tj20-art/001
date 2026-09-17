<template>
  <div class="app-loading">
    <div class="spinner"></div>
    <div class="meta">
      <strong>正在加载数据</strong>
      <p>请稍候，平台正在为你准备最新内容…</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'AppLoading'
}
</script>

<style scoped lang="scss">
.app-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 48px 20px;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
}

.spinner {
  width: 44px;
  height: 44px;
  border: 4px solid #e8edf5;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.meta {
  text-align: left;

  strong {
    display: block;
    color: #1f2937;
    font-size: 16px;
    margin-bottom: 4px;
  }

  p {
    margin: 0;
    color: #6b7280;
    font-size: 13px;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
