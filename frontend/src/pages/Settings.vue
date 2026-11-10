<script setup lang="ts">
import PageFrame from '@/components/PageFrame.vue'
import ComingInSection from '@/components/ComingInSection.vue'
</script>

<template>
  <PageFrame title="Settings" subtitle="Company, numbering, defaults, codes and integrations">
    <ComingInSection icon="lucide-settings" title="Settings" :section="7" text="Company details, invoice numbering, LUT, codes, CBIC rates and Excel sync." />
  </PageFrame>
</template>
