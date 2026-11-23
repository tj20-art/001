<template>
  <el-config-provider :locale="zhCn">
    <RouterView v-slot="{ Component }">
      <component :is="Component" v-if="Component" />
      <main v-else class="page-main startup-view"><AppLoading /></main>
    </RouterView>
  </el-config-provider>
</template>

<script setup>
import AppLoading from '@/components/AppLoading.vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
</script>
