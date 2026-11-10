<script setup lang="ts">
import PageFrame from '@/components/PageFrame.vue'
import ComingInSection from '@/components/ComingInSection.vue'
</script>

<template>
  <PageFrame title="Clients" subtitle="Saved clients fill in every invoice">
    <ComingInSection icon="lucide-users" title="Clients" :section="7" text="Add and edit clients with their default project, wallet, terms and codes." />
  </PageFrame>
</template>
