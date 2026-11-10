<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { DesktopShell, MobileShell, MobileNav, MobileNavItem } from 'frappe-ui'
import AppSidebar from '@/components/AppSidebar.vue'
import { useIsMobile } from '@/composables'
import { NAV } from '@/nav'
import { session } from '@/session'

const isMobile = useIsMobile()
const route = useRoute()
const bare = computed(() => !!route.meta.public)
const mobileItems = computed(() => NAV.flatMap((g) => g.items).filter((i) => !i.managerOnly || session.isManager))
</script>

<template>
  <div v-if="bare" class="min-h-screen bg-surface-base"><RouterView /></div>
  <MobileShell v-else-if="isMobile">
    <RouterView />
    <template #nav>
      <MobileNav>
        <MobileNavItem v-for="i in mobileItems" :key="i.name" :label="i.label.split(' ')[0]" :icon="i.icon" :route="{ name: i.name }" />
      </MobileNav>
    </template>
  </MobileShell>
  <div v-else class="h-screen">
    <DesktopShell>
      <template #sidebar><AppSidebar /></template>
      <RouterView />
    </DesktopShell>
  </div>
</template>
