<template>
  <div class="list-error section-card" role="alert">
    <span>{{ message }}</span>
    <el-button plain type="primary" @click="$emit('retry')">重试</el-button>
  </div>
</template>

<script setup>
defineProps({ message: { type: String, required: true } })
defineEmits(['retry'])
</script>

<style scoped>
.list-error {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px;
  margin-block: 12px;
}
</style>
