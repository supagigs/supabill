<script setup lang="ts">
import { PageHeader, PageHeaderTitle, PageHeaderMobile, PageHeaderMobileTitle } from 'frappe-ui'
import { useIsMobile } from '@/composables'

defineProps<{ title: string; subtitle?: string }>()
const isMobile = useIsMobile()
</script>

<template>
  <PageHeaderMobile v-if="isMobile">
    <PageHeaderMobileTitle :title="title" />
    <template #suffix><slot name="actions" /></template>
  </PageHeaderMobile>
  <PageHeader v-else>
    <div class="flex min-w-0 items-baseline gap-3">
      <PageHeaderTitle :title="title" />
      <span v-if="subtitle" class="truncate text-p-sm text-ink-gray-5">{{ subtitle }}</span>
    </div>
    <div class="flex items-center gap-2"><slot name="actions" /></div>
  </PageHeader>
  <div class="mx-auto w-full max-w-6xl p-4 md:p-6"><slot /></div>
</template>
