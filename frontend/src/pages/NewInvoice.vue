<script setup lang="ts">
import PageFrame from '@/components/PageFrame.vue'
import ComingInSection from '@/components/ComingInSection.vue'
</script>

<template>
  <PageFrame title="New invoice" subtitle="Pick a client, enter the amount, generate">
    <ComingInSection icon="lucide-file-plus" title="New invoice" :section="5" text="The invoice form with live preview and the ready-to-generate checklist." />
  </PageFrame>
</template>
