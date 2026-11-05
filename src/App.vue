<template>
  <div id="app">
    <router-view />
  </div>
</template>

<style lang="scss">
* {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  min-height: 100%;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f3f6fb;
  color: #1f2937;
}

body {
  overflow-y: auto;
}

a {
  text-decoration: none;
}

button,
input,
textarea {
  font-family: inherit;
}

.el-message,
.el-message-box,
.el-dialog {
  border-radius: 18px;
}

.page-shell {
  min-height: 100vh;
  background: radial-gradient(circle at top, rgba(64, 158, 255, 0.1), transparent 28%), #f3f6fb;
}

.page-main {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
}

.section-card {
  background: #fff;
  border-radius: 28px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.08);
}

.muted-text {
  color: #6b7280;
}

.empty-wrap {
  padding: 28px 0 8px;
}

@media screen and (max-width: 960px) {
  .page-main {
    padding: 16px;
  }
}
</style>
