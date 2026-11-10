<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Button } from 'frappe-ui'
import BrandLogo from '@/components/BrandLogo.vue'
import { session, logout } from '@/session'

const route = useRoute()
const openDesk = () => { window.location.href = '/app' }
const needManager = computed(() => route.query.need === 'manager' && session.hasAccess)
</script>

<template>
  <main class="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
    <BrandLogo />
    <h1 class="text-xl font-semibold text-ink-gray-9">
      {{ needManager ? 'Managers only' : 'You don’t have access to SupaBill' }}
    </h1>
    <p class="max-w-md text-p-base text-ink-gray-6">
      <template v-if="needManager">This page needs the <b>SupaBill Manager</b> role.</template>
      <template v-else>
        You are signed in as <b>{{ session.user }}</b>, but this account has no SupaBill role.
        Ask an administrator to give you <b>SupaBill User</b> or <b>SupaBill Manager</b>.
      </template>
    </p>
    <div class="flex gap-2">
      <Button v-if="needManager" label="Back to invoices" variant="solid" :route="{ name: 'NewInvoice' }" />
      <Button v-else label="Switch account" variant="solid" @click="logout" />
      <Button label="Open desk" @click="openDesk" />
    </div>
  </main>
</template>
