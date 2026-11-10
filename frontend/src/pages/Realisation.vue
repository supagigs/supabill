<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FormControl, LoadingIndicator, toast } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'
import { fmtDate, money } from '@/format'

const data = ref<any | null>(null)
const showClosed = ref(false)
const q = ref('')

async function load() {
  try { data.value = await call('supabill.api.edf.realisation', { show_closed: showClosed.value ? 1 : 0 }, { get: true }) } catch (e: any) { toast.error(e.message) }
}
watch(showClosed, load)
const rows = computed(() => {
  const s = q.value.toLowerCase()
  return (data.value?.rows || []).filter((r: any) => !s || [r.name, r.client_name, r.wallet, r.irm_number].join(' ').toLowerCase().includes(s))
})
async function save(r: any, field: string, value: string) {
  if ((r[field] ?? '') === value) return
  try {
    Object.assign(r, await call('supabill.api.edf.update_realisation', { name: r.name, values: { [field]: value } }))
    r.closed = r.edpms_status === 'Closed'
    if (field === 'edpms_status') { toast.success(r.closed ? `${r.name} closed` : `${r.name} reopened`); load() }
  } catch (e: any) { toast.error(e.message); load() }
}
const tone = (r: any) => (r.closed ? 'text-ink-gray-4' : r.days_left < 0 ? 'text-ink-red-5' : r.days_left <= 60 ? 'text-ink-amber-5' : '')
onMounted(load)
</script>

<template>
  <PageFrame title="Realisation tracker" subtitle="Every export invoice until its EDPMS entry closes">
    <div v-if="!data" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <template v-else>
      <div class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <div v-for="k in [
          ['Open entries', data.kpis.open, 'awaiting realisation'],
          ['Due in 60 days', data.kpis.due_60, 'chase these first'],
          ['Past deadline', data.kpis.late, 'speak to the AD bank'],
          ['Paid, not closed', data.kpis.ready_to_close, 'add IRM and close'],
          ['Closed', data.kpis.closed, 'fully realised'],
        ]" :key="k[0]" class="sb-card">
          <div class="text-xs font-medium text-ink-gray-5">{{ k[0] }}</div>
          <div class="mt-1 text-2xl font-bold tabular-nums">{{ k[1] }}</div>
          <div class="text-xs text-ink-gray-5">{{ k[2] }}</div>
        </div>
      </div>
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="w-72"><FormControl v-model="q" placeholder="Search invoice, client, wallet, IRM…" aria-label="Search" /></div>
        <FormControl type="checkbox" label="Show closed" v-model="showClosed" />
        <span class="ml-auto text-p-sm text-ink-gray-5">{{ rows.length }} shown</span>
      </div>
      <div class="sb-card overflow-x-auto !p-0">
        <table class="sb-table min-w-[1000px]">
          <thead><tr><th class="pl-4">Invoice</th><th>Date</th><th>Client</th><th>Wallet</th><th class="sb-num">Amount</th><th>Payment</th><th>Realise by</th><th class="sb-num">Days left</th><th>IRM no.</th><th>EDPMS</th><th>EDF</th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.name">
              <td class="whitespace-nowrap pl-4"><b>{{ r.name }}</b></td>
              <td class="whitespace-nowrap">{{ fmtDate(r.invoice_date) }}</td>
              <td>{{ r.client_name }}</td>
              <td>{{ r.wallet }}</td>
              <td class="sb-num whitespace-nowrap">{{ money(r.grand_total, r.currency) }}</td>
              <td><span class="sb-pill" :class="r.payment_status === 'Received' ? 'sb-ok' : r.payment_status === 'Pending' ? 'sb-mute' : 'sb-warn'">{{ r.payment_status }}</span></td>
              <td class="whitespace-nowrap">{{ fmtDate(r.realise_by) }}</td>
              <td class="sb-num font-semibold" :class="tone(r)">{{ r.closed ? '—' : r.days_left }}</td>
              <td><input class="cell w-36" :class="{ need: r.ready_to_close && !r.irm_number }" :value="r.irm_number" placeholder="IRM no." :aria-label="`IRM number for ${r.name}`" @change="(e: any) => save(r, 'irm_number', e.target.value)" /></td>
              <td>
                <select class="cell" :value="r.edpms_status || 'Open'" :aria-label="`EDPMS status for ${r.name}`" @change="(e: any) => save(r, 'edpms_status', e.target.value)"><option>Open</option><option>Closed</option></select>
                <div v-if="r.closed && r.realised_on" class="text-xs text-ink-gray-5">{{ fmtDate(r.realised_on) }}</div>
              </td>
              <td class="whitespace-nowrap text-xs">{{ r.edf ? r.edf.replace('EDF-', '') + ' ✓' : '—' }}</td>
            </tr>
            <tr v-if="!rows.length"><td colspan="11" class="py-8 text-center text-ink-gray-5">Nothing to track{{ showClosed ? '' : ' — all entries are closed' }}.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="sb-note mt-3">Export proceeds must be realised within {{ data.months }} months of the invoice date (change this in Settings → AD bank). Add the IRM (inward remittance message) number when the AD bank credits the payment, then close the entry once the full value is realised.</p>
    </template>
  </PageFrame>
</template>

<style scoped>
.cell { @apply h-7 min-w-[90px] py-0 leading-7 rounded-3 border border-transparent bg-transparent px-1.5 text-p-sm text-ink-gray-8 hover:border-outline-gray-2 focus:border-outline-gray-4 focus:bg-surface-gray-1 focus:outline-none; }
.cell.need { @apply border-dashed border-outline-amber-3; }
</style>
