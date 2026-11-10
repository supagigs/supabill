<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, FormControl, LoadingIndicator, toast, dialog } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'
import { fmtDate, inr, inrDec, monthLabel } from '@/format'
import { session } from '@/session'

interface Row { [k: string]: any }
const route = useRoute()
const data = ref<{ rows: Row[]; totals: Record<string, number>; months: string[] } | null>(null)
const clients = ref<string[]>([])
const wallets = ref<string[]>([])
const loading = ref(false)
const f = reactive({ search: (route.query.q as string) || '', month: '', client: '', wallet: '', payment_state: '' })

const NUM = new Set(['received_inr', 'bank_charges_usd', 'bank_charges_inr'])
const PAY = ['Pending', 'Partially received', 'Received']
const INV = ['Raised', 'Sent']

async function load() {
  loading.value = true
  try {
    data.value = await call('supabill.api.invoice.list_register', {
      filters: { month: f.month, client: f.client, wallet: f.wallet, payment_state: f.payment_state },
      search: f.search || undefined,
    }, { get: true })
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    loading.value = false
  }
}
let t: number | undefined
watch(f, () => { window.clearTimeout(t); t = window.setTimeout(load, 250) }, { deep: true })

function stateOf(r: Row): string {
  if (r.docstatus === 2) return 'Cancelled'
  if (r.payment_status !== 'Pending') return r.payment_status
  return r.due_date && new Date(r.due_date + 'T00:00') < new Date(new Date().toDateString()) ? 'Overdue' : 'Pending'
}
async function saveCell(row: Row, field: string, raw: any) {
  const value = NUM.has(field) ? (raw === '' || raw === null ? '' : Number(raw)) : raw
  if ((row[field] ?? '') === value) return
  try {
    const before = row.payment_status
    const updated = await call('supabill.api.invoice.update_register', { name: row.name, values: { [field]: value } })
    Object.assign(row, updated)
    row.payment_state = stateOf(row)
    if (field === 'received_inr' && before !== updated.payment_status) toast.success(`Payment status set to “${updated.payment_status}”`)
    recompute()
  } catch (e: any) {
    toast.error(e.message)
  }
}
function recompute() {
  if (!data.value) return
  const live = data.value.rows.filter((r) => r.docstatus === 1)
  const sum = (k: string, rows = live) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0)
  Object.assign(data.value.totals, {
    count: live.length, amount_inr: sum('amount_inr'), received_inr: sum('received_inr'), forex_gain: sum('forex_gain'),
    outstanding_inr: sum('amount_inr', live.filter((r) => r.payment_state !== 'Received')),
    overdue: live.filter((r) => r.payment_state === 'Overdue').length,
    missing_wallet_ref: live.filter((r) => !r.wallet_reference && r.wallet !== 'Upwork').length,
  })
}
function cancelInvoice(row: Row) {
  dialog.confirm({
    title: `Cancel ${row.name}?`,
    message: 'The invoice stays in the register marked Cancelled. This cannot be undone.',
    confirmLabel: 'Cancel invoice',
    theme: 'red',
    onConfirm: async () => {
      try {
        await call('supabill.api.invoice.cancel_invoice', { name: row.name })
        toast.success(`${row.name} cancelled`)
        load()
      } catch (e: any) { toast.error(e.message) }
    },
  } as any)
}

const COLS = ['Sr.', 'Invoice no.', 'Upwork invoice', 'Upwork holder', 'Wallet ref. no.', 'Invoice date', 'Month', 'Client', 'Description', 'Wallet', 'GST return', 'Cur.', 'Amount', 'CBIC rate', 'Amount in INR', 'Received (₹)', 'Forex gain', 'Net received', 'Bank charges ($)', 'Bank charges (₹)', 'Payment status', 'Invoice status', 'Excel', '']
const XL = ['Sr. No.', 'Original Invoice Number', 'Upwork Invoice', 'Upwork Account Holder', 'Wallet Reference Invoice Number', 'Invoice Date', 'Month', 'Client Name', 'Description', 'Mode of Payment (Wallet Name)', 'GST Return', 'Currency', 'Invoice Amount in Original Currency', 'CBIC Rate Rs./$', 'Invoice Amount in INR', 'Received', 'Forex Gain', 'Net Received', 'Bank Conversion Charges (In $)', 'Bank Conversion Charges (In Rs)', 'Payment Status', 'Invoice Status']
const rows = computed(() => data.value?.rows || [])
const live = computed(() => rows.value.filter((r) => r.docstatus === 1))
const sameCur = computed(() => new Set(live.value.map((r) => r.currency)).size === 1)
const has = (v: any) => v !== null && v !== undefined && v !== '' && Number(v) !== 0
const blank0 = (v: any) => (has(v) ? v : '')
const syncCls = (s: string) => ({ Synced: 'sb-ok', Failed: 'sb-bad', Queued: 'sb-warn' } as Record<string, string>)[s] || 'sb-mute'
const walletName = (r: Row) => (r.wallet === 'Others' && r.wallet_name_other ? r.wallet_name_other : r.wallet)
const sumOrig = computed(() => live.value.reduce((a, r) => a + r.grand_total, 0))
const sumNet = computed(() => live.value.reduce((a, r) => a + (Number(r.net_received) || 0), 0))

function exportCsv() {
  const q = (v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = [XL.map(q).join(',')].concat(rows.value.map((r, i) => [
    i + 1, r.name, r.upwork_invoice, r.upwork_account_holder, r.wallet_reference, r.invoice_date, Number(String(r.invoice_date).slice(5, 7)),
    r.client_name, r.register_description, walletName(r), r.gst_return_period, r.currency, r.grand_total, r.cbic_rate, r.amount_inr,
    blank0(r.received_inr), has(r.received_inr) ? r.forex_gain : '', has(r.received_inr) ? r.net_received : '', blank0(r.bank_charges_usd), blank0(r.bank_charges_inr), r.payment_state, r.docstatus === 2 ? 'Cancelled' : r.invoice_status,
  ].map(q).join(',')))
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\n')], { type: 'text/csv' }))
  a.download = `Sales_Register_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
}
async function syncNow() {
  try { toast.success((await call('supabill.api.integrations.excel_sync_now')).message); load() } catch (e: any) { toast.error(e.message) }
}

onMounted(async () => {
  load()
  try {
    const b = await call('supabill.api.invoice.bootstrap', {}, { get: true })
    clients.value = b.clients.map((c: any) => c.name)
    wallets.value = b.wallets.map((w: any) => w.name)
  } catch { /* filters stay empty */ }
})
</script>

<template>
  <PageFrame title="Sales register" subtitle="Mirrors your Excel workbook">
    <template #actions>
      <Button label="Export .csv" icon-left="lucide-download" @click="exportCsv" />
      <Button v-if="session.isManager" label="Sync with Excel" icon-left="lucide-refresh-cw" @click="syncNow" />
      <Button variant="solid" label="New invoice" icon-left="lucide-plus" :route="{ name: 'NewInvoice' }" />
    </template>

    <div v-if="!data" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <template v-else>
      <div class="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div class="sb-card"><div class="text-xs text-ink-gray-5">Invoices</div><div class="mt-1 text-xl font-semibold tabular-nums">{{ data.totals.count }}</div><div class="text-xs text-ink-gray-5">{{ data.totals.missing_wallet_ref }} missing wallet ref</div></div>
        <div class="sb-card"><div class="text-xs text-ink-gray-5">Invoiced (INR)</div><div class="mt-1 text-xl font-semibold tabular-nums">{{ inr(data.totals.amount_inr) }}</div><div class="text-xs text-ink-gray-5">at CBIC rate</div></div>
        <div class="sb-card"><div class="text-xs text-ink-gray-5">Received</div><div class="mt-1 text-xl font-semibold tabular-nums">{{ inr(data.totals.received_inr) }}</div><div class="text-xs text-ink-gray-5">credited in INR</div></div>
        <div class="sb-card"><div class="text-xs text-ink-gray-5">Outstanding</div><div class="mt-1 text-xl font-semibold tabular-nums">{{ inr(data.totals.outstanding_inr) }}</div><div class="text-xs" :class="data.totals.overdue ? 'text-ink-red-5' : 'text-ink-gray-5'">{{ data.totals.overdue }} overdue</div></div>
        <div class="sb-card"><div class="text-xs text-ink-gray-5">Forex gain</div><div class="mt-1 text-xl font-semibold tabular-nums" :class="data.totals.forex_gain < 0 ? 'text-ink-red-5' : ''">{{ inr(data.totals.forex_gain) }}</div><div class="text-xs text-ink-gray-5">on received</div></div>
      </div>

      <div class="mb-3 flex flex-wrap items-end gap-2">
        <div class="w-64"><FormControl v-model="f.search" placeholder="Search invoice, client, wallet ref…" aria-label="Search register" /></div>
        <div class="w-44"><FormControl type="select" v-model="f.month" :options="[{ label: 'All months', value: '' }, ...data.months.map((m) => ({ label: monthLabel(m), value: m }))]" aria-label="Month" /></div>
        <div class="w-52"><FormControl type="select" v-model="f.client" :options="[{ label: 'All clients', value: '' }, ...clients]" aria-label="Client" /></div>
        <div class="w-40"><FormControl type="select" v-model="f.wallet" :options="[{ label: 'All wallets', value: '' }, ...wallets]" aria-label="Wallet" /></div>
        <div class="w-48"><FormControl type="select" v-model="f.payment_state" :options="[{ label: 'All payment status', value: '' }, 'Pending', 'Overdue', 'Partially received', 'Received', 'Cancelled']" aria-label="Payment status" /></div>
        <LoadingIndicator v-if="loading" class="mb-1.5 size-4 text-ink-gray-5" />
        <span class="ml-auto pb-1.5 text-xs text-ink-gray-5">{{ rows.length }} rows</span>
      </div>

      <div class="max-h-[calc(100vh-330px)] min-h-[260px] overflow-auto rounded-6 border border-outline-gray-2 bg-surface-base">
        <table class="reg w-full min-w-[2100px] border-separate border-spacing-0 text-p-sm">
          <thead>
            <tr><th v-for="(c, j) in COLS" :key="j" :class="[j === 0 ? 'stk1' : j === 1 ? 'stk2' : '', j >= 12 && j <= 19 ? 'text-right' : '']">{{ c }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="r.name" :class="{ 'opacity-60': r.docstatus === 2 }" :data-invoice="r.name">
              <td class="stk1 text-ink-gray-5">{{ i + 1 }}</td>
              <td class="stk2 font-semibold">{{ r.name }}</td>
              <template v-if="r.docstatus === 1">
                <td><input class="cell" :value="r.upwork_invoice" :aria-label="`Upwork invoice for ${r.name}`" @change="(e: any) => saveCell(r, 'upwork_invoice', e.target.value)" /></td>
                <td><input class="cell" :value="r.upwork_account_holder" :aria-label="`Upwork holder for ${r.name}`" @change="(e: any) => saveCell(r, 'upwork_account_holder', e.target.value)" /></td>
                <td><input class="cell" :class="{ need: !r.wallet_reference && r.wallet !== 'Upwork' }" :value="r.wallet_reference" placeholder="add ref" :aria-label="`Wallet reference for ${r.name}`" @change="(e: any) => saveCell(r, 'wallet_reference', e.target.value)" /></td>
              </template>
              <template v-else><td>{{ r.upwork_invoice }}</td><td>{{ r.upwork_account_holder }}</td><td>{{ r.wallet_reference }}</td></template>
              <td>{{ fmtDate(r.invoice_date) }}</td>
              <td class="text-ink-gray-5">{{ Number(String(r.invoice_date).slice(5, 7)) }}</td>
              <td>{{ r.client_name }}</td>
              <td class="max-w-[220px] truncate" :title="r.register_description">{{ r.register_description }}</td>
              <td>{{ walletName(r) }}</td>
              <td>{{ r.gst_return_period }}</td>
              <td>{{ r.currency }}</td>
              <td class="text-right tabular-nums">{{ inrDec(r.grand_total) }}</td>
              <td class="text-right tabular-nums">{{ r.currency === 'INR' ? '—' : r.cbic_rate }}</td>
              <td class="text-right tabular-nums text-ink-gray-6">{{ inrDec(r.amount_inr) }}</td>
              <template v-if="r.docstatus === 1">
                <td class="text-right"><input class="cell w-28 text-right" type="number" step="0.01" :class="{ need: !has(r.received_inr) }" :value="blank0(r.received_inr)" placeholder="₹ received" :aria-label="`Received for ${r.name}`" @change="(e: any) => saveCell(r, 'received_inr', e.target.value)" /></td>
                <td class="text-right tabular-nums" :class="r.forex_gain < 0 ? 'text-ink-red-5' : r.forex_gain > 0 ? 'text-ink-green-5' : ''">{{ has(r.received_inr) ? inrDec(r.forex_gain) : '' }}</td>
                <td class="text-right tabular-nums text-ink-gray-6">{{ has(r.received_inr) ? inrDec(r.net_received) : '' }}</td>
                <td class="text-right"><input class="cell w-24 text-right" type="number" step="0.01" :value="blank0(r.bank_charges_usd)" :aria-label="`Bank charges in foreign currency for ${r.name}`" @change="(e: any) => saveCell(r, 'bank_charges_usd', e.target.value)" /></td>
                <td class="text-right"><input class="cell w-24 text-right" type="number" step="0.01" :value="blank0(r.bank_charges_inr)" :aria-label="`Bank charges in INR for ${r.name}`" @change="(e: any) => saveCell(r, 'bank_charges_inr', e.target.value)" /></td>
                <td>
                  <select class="cell" :value="r.payment_status" :aria-label="`Payment status for ${r.name}`" @change="(e: any) => saveCell(r, 'payment_status', e.target.value)"><option v-for="o in PAY" :key="o">{{ o }}</option></select>
                  <span v-if="r.payment_state === 'Overdue'" class="sb-pill sb-bad ml-1">Overdue</span>
                </td>
                <td><select class="cell" :value="r.invoice_status" :aria-label="`Invoice status for ${r.name}`" @change="(e: any) => saveCell(r, 'invoice_status', e.target.value)"><option v-for="o in INV" :key="o">{{ o }}</option></select></td>
              </template>
              <template v-else>
                <td /><td /><td /><td /><td /><td><span class="sb-pill sb-mute">Cancelled</span></td><td>Cancelled</td>
              </template>
              <td><span class="sb-pill" :class="syncCls(r.excel_sync_status)" :title="r.excel_row ? 'Excel row ' + r.excel_row : ''">{{ r.excel_sync_status === 'Synced' ? '✓ row ' + r.excel_row : r.excel_sync_status }}</span></td>
              <td class="whitespace-nowrap">
                <a class="sb-link" :href="`/api/method/supabill.api.output.download?name=${encodeURIComponent(r.name)}&fmt=pdf`" target="_blank" rel="noopener">PDF</a>
                <span class="mx-1 text-ink-gray-3">·</span>
                <a class="sb-link" :href="`/api/method/supabill.api.output.download?name=${encodeURIComponent(r.name)}&fmt=docx`">DOCX</a>
                <template v-if="session.isManager && r.docstatus === 1"><span class="mx-1 text-ink-gray-3">·</span><button type="button" class="sb-link !text-ink-red-5" @click="cancelInvoice(r)">Cancel</button></template>
              </td>
            </tr>
            <tr v-if="!rows.length"><td :colspan="COLS.length" class="py-10 text-center text-ink-gray-5">No invoices match these filters</td></tr>
          </tbody>
          <tfoot v-if="rows.length">
            <tr>
              <td class="stk1" /><td class="stk2">Total</td><td colspan="10" />
              <td class="text-right">{{ sameCur ? inrDec(sumOrig) : 'mixed' }}</td><td />
              <td class="text-right">{{ inrDec(data.totals.amount_inr) }}</td><td class="text-right">{{ inrDec(data.totals.received_inr) }}</td>
              <td class="text-right">{{ inrDec(data.totals.forex_gain) }}</td><td class="text-right">{{ inrDec(sumNet) }}</td>
              <td colspan="6" />
            </tr>
          </tfoot>
        </table>
      </div>
      <p class="sb-note mt-2">Dashed cells are the ones your team fills in later — edit here or in Excel; both stay in sync. Received is the INR credited in IDFC FIRST Bank. Net received = Received − Bank charges (₹). Entering Received sets the payment status.</p>
    </template>
  </PageFrame>
</template>

<style scoped>
.reg th { @apply sticky top-0 z-[2] whitespace-nowrap border-b border-outline-gray-2 bg-surface-gray-2 px-2 py-2 text-left text-xs font-semibold text-ink-gray-6; }
.reg td { @apply whitespace-nowrap border-b border-outline-gray-1 bg-surface-base px-2 py-1; }
.reg .stk1 { @apply sticky left-0 z-[1] min-w-[44px]; }
.reg .stk2 { @apply sticky left-[44px] z-[1]; box-shadow: 1px 0 0 var(--outline-gray-2, #e2e2e2); }
.reg th.stk1, .reg th.stk2 { @apply z-[3]; }
.reg tfoot td { @apply sticky bottom-0 border-t border-outline-gray-2 bg-surface-gray-2 py-2 font-semibold tabular-nums; }
.cell { @apply h-7 min-w-[90px] py-0 leading-7 rounded-3 border border-transparent bg-transparent px-1.5 text-p-sm text-ink-gray-8 hover:border-outline-gray-2 focus:border-outline-gray-4 focus:bg-surface-gray-1 focus:outline-none; }
.cell.need { @apply border-dashed border-outline-amber-3; }
</style>
