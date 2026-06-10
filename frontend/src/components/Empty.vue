<template>
  <div class="flex items-center justify-center py-12">
    <div class="text-center">
      <div class="text-4xl mb-2">{{ icon }}</div>
      <h3 class="text-base font-medium text-gray-900">{{ title }}</h3>
      <p class="text-sm text-gray-500 mt-1">{{ description }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  icon: {
    type: String,
    default: '📭'
  },
  title: {
    type: String,
    default: '暂无数据'
  },
  description: {
    type: String,
    default: ''
  }
})
</script>
