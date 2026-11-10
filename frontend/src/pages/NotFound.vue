<script setup lang="ts">
import { Button } from 'frappe-ui'
</script>

<template>
  <main class="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
    <p class="text-4xl font-bold text-ink-gray-3">404</p>
    <h1 class="text-lg font-semibold text-ink-gray-9">This page doesn’t exist</h1>
    <Button label="Go to SupaBill" variant="solid" :route="{ name: 'NewInvoice' }" />
  </main>
</template>
