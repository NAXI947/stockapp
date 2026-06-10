<template>
  <div class="flex items-center justify-center py-12">
    <div class="flex flex-col items-center space-y-3">
      <div class="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin"></div>
      <p class="text-sm text-gray-500">{{ text }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  text: {
    type: String,
    default: '加载中...'
  }
})
</script>
