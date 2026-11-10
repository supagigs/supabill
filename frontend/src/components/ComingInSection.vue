<script setup lang="ts">
defineProps<{ icon: string; title: string; section: number; text: string }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center rounded-xl border border-dashed border-outline-gray-2 px-6 py-16 text-center">
    <span :class="[icon, 'mb-3 size-8 text-ink-gray-4']" aria-hidden="true" />
    <p class="text-base font-semibold text-ink-gray-8">{{ title }}</p>
    <p class="mt-1 max-w-md text-p-sm text-ink-gray-5">{{ text }}</p>
    <p class="mt-3 text-xs font-medium text-ink-gray-4">Built in Section {{ section }}</p>
  </div>
</template>
