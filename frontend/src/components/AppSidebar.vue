<script setup lang="ts">
import { computed, ref } from 'vue'
import { Sidebar, SidebarHeader, SidebarItem, SidebarLabel, SidebarCollapseToggle, useColorScheme } from 'frappe-ui'
import BrandLogo from './BrandLogo.vue'
import { NAV } from '@/nav'
import { session, logout } from '@/session'

const collapsed = ref(localStorageGet('sb_sidebar_collapsed') === '1')
function onCollapse(v: unknown) {
  collapsed.value = !!v
  localStorageSet('sb_sidebar_collapsed', v ? '1' : '0')
}
const { resolvedColorScheme, setColorScheme } = useColorScheme()

const groups = computed(() =>
  NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.managerOnly || session.isManager) })).filter((g) => g.items.length),
)

const menu = computed(() => [
  { label: session.fullName || session.user, disabled: true },
  {
    label: resolvedColorScheme.value === 'dark' ? 'Light mode' : 'Dark mode',
    icon: resolvedColorScheme.value === 'dark' ? 'lucide-sun' : 'lucide-moon',
    onClick: () => setColorScheme(resolvedColorScheme.value === 'dark' ? 'light' : 'dark'),
  },
  { label: 'Open desk', icon: 'lucide-app-window', onClick: () => (window.location.href = '/app') },
  { label: 'Log out', icon: 'lucide-log-out', onClick: logout },
])

function localStorageGet(k: string) {
  try { return localStorage.getItem(k) } catch { return null }
}
function localStorageSet(k: string, v: string) {
  try { localStorage.setItem(k, v) } catch { /* private mode */ }
}
</script>

<template>
  <Sidebar class="h-full" :collapsed="collapsed" @update:collapsed="onCollapse" aria-label="SupaBill">
    <SidebarHeader title="SupaBill" subtitle="Invoices · Register" :menu-items="menu">
      <template #prefix><BrandLogo /></template>
    </SidebarHeader>
    <div class="flex-1 overflow-y-auto px-2 py-1">
      <template v-for="g in groups" :key="g.label">
        <SidebarLabel divider>{{ g.label }}</SidebarLabel>
        <SidebarItem
          v-for="item in g.items"
          :key="item.name"
          :label="item.label"
          :icon="item.icon"
          :route="{ name: item.name }"
        />
      </template>
    </div>
    <div class="mt-auto px-2 pb-2"><SidebarCollapseToggle /></div>
  </Sidebar>
</template>
