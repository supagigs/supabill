<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { call } from '@/api'
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
const sync = ref<any>(null)
async function loadSync() {
  try { sync.value = await call('supabill.api.integrations.sync_status', {}, { get: true }) } catch { sync.value = null }
}
onMounted(() => { loadSync(); window.setInterval(loadSync, 60000) })
const ago = (d?: string) => {
  if (!d) return 'never'
  const m = Math.round((Date.now() - new Date(d.replace(' ', 'T')).getTime()) / 60000)
  return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : Math.round(m / 60) + ' h ago'
}

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
    <div class="mt-auto px-2 pb-2">
      <div v-if="sync && !collapsed" class="mb-2 rounded-5 border border-outline-gray-2 bg-surface-base p-3 text-xs" data-testid="sync-card">
        <div class="flex items-center gap-2 text-p-sm font-medium text-ink-gray-8">
          <span class="size-2 rounded-full" :class="!sync.enabled ? 'bg-surface-gray-5' : sync.failed ? 'bg-surface-red-6' : 'bg-surface-green-5'" aria-hidden="true" />
          {{ !sync.enabled ? 'Excel sync off' : sync.failed ? sync.failed + ' not synced' : 'Synced with Excel' }}
        </div>
        <div v-if="sync.enabled" class="mt-1 text-ink-gray-5">Sheet {{ sync.worksheet }} · pushed {{ ago(sync.last_push) }} · read {{ ago(sync.last_pull) }}<span v-if="sync.waiting"> · {{ sync.waiting }} waiting</span></div>
        <div v-else class="mt-1 text-ink-gray-5">Turn it on in Settings once Microsoft 365 is connected.</div>
      </div>
      <SidebarCollapseToggle />
    </div>
  </Sidebar>
</template>
