<script setup lang="ts">
import PageFrame from '@/components/PageFrame.vue'
import ComingInSection from '@/components/ComingInSection.vue'
</script>

<template>
  <PageFrame title="Wallets & banks" subtitle="Collection accounts printed on invoices">
    <ComingInSection icon="lucide-wallet" title="Wallets & banks" :section="7" text="Bank details for each wallet, shown under Bank Transfer Details." />
  </PageFrame>
</template>
