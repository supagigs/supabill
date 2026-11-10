<script setup lang="ts">
import { onMounted } from 'vue'
import { FrappeUIProvider, LoadingIndicator, Button } from 'frappe-ui'
import AppShell from '@/layouts/AppShell.vue'
import { session, loadSession } from '@/session'

onMounted(loadSession)
</script>

<template>
  <FrappeUIProvider>
    <div v-if="!session.ready" class="flex h-screen items-center justify-center bg-surface-base text-ink-gray-5">
      <LoadingIndicator class="size-6" />
    </div>
    <div v-else-if="session.error" class="flex h-screen flex-col items-center justify-center gap-3 bg-surface-base p-6 text-center">
      <p class="text-lg font-semibold text-ink-gray-9">SupaBill could not reach the server</p>
      <p class="text-p-sm text-ink-gray-6">{{ session.error }}</p>
      <Button label="Try again" variant="solid" @click="() => { session.ready = false; loadSession() }" />
    </div>
    <AppShell v-else />
  </FrappeUIProvider>
</template>
