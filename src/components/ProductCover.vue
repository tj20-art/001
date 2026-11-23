<template>
  <img
    v-if="src && failedSrc !== src"
    :src="src"
    :alt="alt"
    :loading="loading"
    decoding="async"
    @error="failedSrc = src"
  />
  <span v-else class="cover-placeholder" aria-hidden="true"
    ><el-icon><Box /></el-icon
  ></span>
</template>

<script setup>
import { ref } from 'vue'
defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  loading: { type: String, default: 'lazy' }
})
const failedSrc = ref('')
</script>

<style scoped>
img,
.cover-placeholder {
  display: block;
  width: 100%;
  height: 100%;
}
img {
  object-fit: cover;
}
.cover-placeholder {
  display: grid;
  place-items: center;
  color: var(--mall-muted);
  background: #eee9e0;
  font-size: 1.75rem;
}
</style>
