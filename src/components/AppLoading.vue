<template>
  <div class="app-loading" role="status">
    <div class="spinner" aria-hidden="true"></div>
    <div class="meta">
      <strong>加载中…</strong>
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
  background: var(--mall-surface);
}

.spinner {
  width: 44px;
  height: 44px;
  border: 4px solid #e8edf5;
  border-top-color: var(--mall-accent);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

.meta {
  text-align: left;

  strong {
    display: block;
    color: var(--mall-ink);
    font-size: 16px;
    margin-bottom: 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
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
