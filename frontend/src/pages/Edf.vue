<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Dialog, FormControl, LoadingIndicator, toast, dialog } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'
import { fmtDate, inr, money, today } from '@/format'
import { session } from '@/session'

const months = ref<any[] | null>(null)
const month = ref('')
const edf = ref<any | null>(null)
const busy = ref(false)
const fileOpen = ref(false)
const fileForm = ref({ bank_reference: '', filed_on: today() })

const filed = computed(() => edf.value?.status === 'Filed')
const banner = computed(() => {
  const e = edf.value
  if (!e) return null
  if (filed.value) return { tone: 'ok', big: '✓', small: '' }
  const d = e.days_left
  return { tone: d < 0 ? 'late' : 'due', big: String(Math.abs(d)), small: d < 0 ? 'days late' : 'days left' }
})
const CATS = ['Others', 'Custom (DTA units)', 'SEZ', '100% EOU', 'Warehouse export']
const TYPES = ['Service — software', 'Service — non-software']

async function loadMonths() {
  months.value = await call('supabill.api.edf.list_months', {}, { get: true })
  if (!month.value) {
    const pending = [...months.value!].reverse().find((m) => m.invoices && m.status !== 'Filed')
    month.value = (pending || months.value![0]).month
  }
}
async function loadEdf() {
  if (!month.value) return
  edf.value = null
  try {
    edf.value = await call('supabill.api.edf.get_edf', { month: month.value }, { get: true })
  } catch (e: any) { toast.error(e.message) }
}
watch(month, loadEdf)

async function save(values: Record<string, any> = {}, lines: any[] = []) {
  try {
    edf.value = await call('supabill.api.edf.save_edf', { month: month.value, values, lines })
  } catch (e: any) { toast.error(e.message); await loadEdf() }
}
function saveLine(l: any, field: string, raw: string) {
  const v = field === 'net_realisable_value' ? Number(raw) : raw
  if ((l[field] ?? '') === v) return
  save({}, [{ invoice: l.invoice, [field]: v }])
}
async function markFiled() {
  busy.value = true
  try {
    edf.value = await call('supabill.api.edf.mark_filed', { month: month.value, ...fileForm.value })
    fileOpen.value = false
    toast.success('Marked as filed')
    await loadMonths()
  } catch (e: any) { toast.error(e.message) } finally { busy.value = false }
}
function reopen() {
  dialog.confirm({
    title: 'Reopen this EDF?', message: 'It goes back to draft and follows the register again. The filing date and reference are cleared.',
    confirmLabel: 'Reopen',
    onConfirm: async () => {
      try { edf.value = await call('supabill.api.edf.reopen', { month: month.value }); await loadMonths(); toast.success('Reopened') } catch (e: any) { toast.error(e.message) }
    },
  } as any)
}
function download(fmt: 'pdf' | 'csv') {
  window.open(`/api/method/supabill.api.edf.download?month=${month.value}&fmt=${fmt}`, '_blank')
}
const totalAmt = computed(() => {
  const ls = edf.value?.lines || []
  const curs = new Set(ls.map((l: any) => l.currency))
  if (curs.size !== 1) return null
  const c = ls[0].currency
  return { c, amt: ls.reduce((a: number, l: any) => a + Number(l.amount || 0), 0), nrv: ls.reduce((a: number, l: any) => a + Number(l.net_realisable_value || 0), 0) }
})
onMounted(async () => { try { await loadMonths() } catch (e: any) { toast.error(e.message) } })
</script>

<template>
  <PageFrame title="EDF filing" subtitle="Monthly Export Declaration Form · RBI Annex layout">
    <template #actions>
      <Button label="CSV" icon-left="lucide-sheet" :disabled="!edf?.lines?.length" @click="download('csv')" />
      <Button label="PDF" icon-left="lucide-download" :disabled="!edf?.lines?.length" @click="download('pdf')" />
      <Button v-if="session.isManager && !filed" variant="solid" label="Mark as filed" :disabled="!edf?.lines?.length" @click="fileOpen = true" />
      <Button v-if="session.isManager && filed" label="Reopen" @click="reopen" />
    </template>

    <div v-if="!months" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <template v-else>
      <div class="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Invoice months">
        <button v-for="m in months" :key="m.month" type="button" role="tab" :aria-selected="m.month === month"
          class="min-w-36 rounded-5 border px-3 py-2 text-left text-p-sm" :class="m.month === month ? 'border-outline-gray-5 bg-surface-gray-2' : 'border-outline-gray-2 hover:bg-surface-gray-1'"
          @click="month = m.month">
          <b class="block">{{ m.label }}</b>
          <span v-if="m.status === 'Filed'" class="text-xs text-ink-green-5">✓ Filed {{ fmtDate(m.filed_on) }}</span>
          <span v-else-if="!m.invoices" class="text-xs text-ink-gray-5">No export invoices</span>
          <span v-else class="text-xs" :class="m.days_left < 0 ? 'text-ink-red-5' : 'text-ink-amber-5'">{{ m.days_left < 0 ? 'Overdue' : 'Due ' + fmtDate(m.due_date) }}</span>
          <span class="block text-xs text-ink-gray-5">{{ m.invoices }} invoice{{ m.invoices === 1 ? '' : 's' }}</span>
        </button>
      </div>

      <div v-if="!edf" class="flex justify-center py-16"><LoadingIndicator class="size-6" /></div>
      <template v-else>
        <div v-if="banner" class="mb-4 flex items-center gap-4 rounded-6 border p-4"
          :class="{ 'border-outline-green-2 bg-surface-green-1': banner.tone === 'ok', 'border-outline-amber-2 bg-surface-amber-1': banner.tone === 'due', 'border-outline-red-2 bg-surface-red-1': banner.tone === 'late' }">
          <div class="min-w-16 text-center text-2xl font-bold leading-none">{{ banner.big }}<small class="block text-xs font-medium text-ink-gray-5">{{ banner.small }}</small></div>
          <div class="text-p-sm">
            <template v-if="filed"><b>EDF filed with {{ edf.settings.ad_bank_name || 'the AD bank' }}</b>
              <div class="sb-note">Filed on {{ fmtDate(edf.filed_on) }}<span v-if="edf.bank_reference"> · Ref {{ edf.bank_reference }}</span>. Filed EDFs are frozen; reopen to change.</div></template>
            <template v-else><b>EDF {{ edf.days_left < 0 ? 'was' : 'is' }} due {{ fmtDate(edf.due_date) }}</b>
              <div class="sb-note">{{ edf.lines.length }} export invoice{{ edf.lines.length === 1 ? '' : 's' }} · file with {{ edf.settings.ad_bank_name || 'your AD bank' }} within 30 days of month-end.
                <span v-if="edf.days_left < 0">Late EDFs can lead the bank to hold inward payments.</span></div></template>
          </div>
        </div>

        <div v-if="edf.missing.length && !filed" class="sb-card mb-4">
          <div class="sb-sect text-ink-amber-6">Fill in before filing</div>
          <ul class="list-disc pl-5 text-p-sm text-ink-gray-7"><li v-for="m in edf.missing" :key="m">{{ m }}</li></ul>
        </div>

        <div class="mb-4 flex flex-wrap items-end gap-3">
          <div class="w-56"><FormControl type="select" label="Type of export" :model-value="edf.export_type" :options="TYPES" :disabled="filed" @update:model-value="(v: string) => save({ export_type: v })" /></div>
          <div class="w-56"><FormControl type="select" label="Category of exporter" :model-value="edf.exporter_category" :options="CATS" :disabled="filed" @update:model-value="(v: string) => save({ exporter_category: v })" /></div>
          <div class="w-44"><FormControl label="Form No. (from bank)" :model-value="edf.form_no" placeholder="optional" @change="(e: any) => save({ form_no: e.target.value })" /></div>
        </div>

        <div v-if="!edf.lines.length" class="sb-card py-10 text-center text-p-sm text-ink-gray-5">No export invoices dated in this month yet.</div>
        <section v-else class="sb-card overflow-x-auto !p-0" aria-label="2B. Details of export value of services">
          <div class="sb-sect px-4 pt-4">2B. Services provided <span class="sb-note normal-case tracking-normal">Net realisable value defaults to the invoice amount — lower it where a wallet deducts fees.</span></div>
          <table class="sb-table min-w-[1000px]">
            <thead><tr><th class="pl-4">#</th><th>Service recipient</th><th>Country</th><th>Invoice</th><th>Date</th><th class="sb-num">Amount</th><th class="sb-num">Net realisable</th><th>Contract no. &amp; date</th><th>Description</th><th>SAC</th><th>Remarks</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in edf.lines" :key="l.invoice">
                <td class="pl-4">{{ i + 1 }}</td>
                <td><b>{{ l.client_name }}</b><div class="max-w-56 truncate text-xs text-ink-gray-5" :title="l.address">{{ l.address || 'address missing' }}</div></td>
                <td :class="{ 'text-ink-amber-6': !l.country }">{{ l.country || 'missing' }}</td>
                <td class="whitespace-nowrap">{{ l.invoice }}</td>
                <td class="whitespace-nowrap">{{ fmtDate(l.invoice_date) }}</td>
                <td class="sb-num whitespace-nowrap">{{ money(l.amount, l.currency) }}</td>
                <td class="sb-num"><input class="cell w-28 text-right" type="number" step="0.01" min="0" :value="l.net_realisable_value" :disabled="filed" :aria-label="`Net realisable value for ${l.invoice}`" @change="(e: any) => saveLine(l, 'net_realisable_value', e.target.value)" /></td>
                <td><input class="cell w-32" :value="l.contract" placeholder="optional" :disabled="filed" :aria-label="`Contract for ${l.invoice}`" @change="(e: any) => saveLine(l, 'contract', e.target.value)" /></td>
                <td class="max-w-64 truncate" :title="l.description">{{ l.description }}</td>
                <td>{{ l.sac_code }}</td>
                <td><input class="cell w-40" :value="l.remarks" :disabled="filed" :aria-label="`Remarks for ${l.invoice}`" @change="(e: any) => saveLine(l, 'remarks', e.target.value)" /></td>
              </tr>
            </tbody>
            <tfoot><tr class="font-semibold"><td class="pl-4" colspan="5">Total · {{ inr(edf.total_inr) }} at CBIC rates</td>
              <td class="sb-num">{{ totalAmt ? money(totalAmt.amt, totalAmt.c) : 'mixed' }}</td><td class="sb-num">{{ totalAmt ? money(totalAmt.nrv, totalAmt.c) : '' }}</td><td colspan="4"></td></tr></tfoot>
          </table>
        </section>

        <div class="mt-4 grid gap-4 md:grid-cols-2">
          <div class="sb-card text-p-sm">
            <div class="sb-sect">Section 1 &amp; 4 (filled from Settings)</div>
            <dl class="grid grid-cols-[150px_1fr] gap-y-1">
              <dt class="text-ink-gray-5">AD bank</dt><dd>{{ edf.settings.ad_bank_name || '—' }} <span class="text-ink-gray-5">{{ edf.settings.ad_code ? '· AD code ' + edf.settings.ad_code : '· AD code not set' }}</span></dd>
              <dt class="text-ink-gray-5">Countries</dt><dd>{{ edf.countries.join(', ') || '—' }}</dd>
              <dt class="text-ink-gray-5">Realise by</dt><dd>{{ fmtDate(edf.realise_by) || '—' }}</dd>
              <dt class="text-ink-gray-5">Value in words</dt><dd>{{ edf.total_in_words || '—' }}</dd>
              <dt class="text-ink-gray-5">Signatory</dt><dd>{{ edf.settings.signatory_name || '—' }}{{ edf.settings.signatory_designation ? ', ' + edf.settings.signatory_designation : '' }}</dd>
            </dl>
          </div>
          <div class="sb-card sb-note">
            <b class="text-ink-gray-8">How this is prepared.</b> One consolidated EDF per invoice month for all export (LUT) invoices, laid out like the RBI Annex. All wallets settle into one AD bank, so there is one form per month. Mode of delivery is Internet and realisation is “Others”; Sections 2A and 3 are marked not applicable for services. Drafts follow the register; once marked filed the form is frozen and each invoice is linked to it. Confirm the submission channel with your AD bank and CA before filing.
          </div>
        </div>
      </template>
    </template>

    <Dialog v-model:open="fileOpen" title="Mark EDF as filed">
        <form class="grid gap-3" @submit.prevent="markFiled">
          <FormControl type="date" label="Filed on" v-model="fileForm.filed_on" />
          <FormControl label="Bank / EDPMS reference (optional)" v-model="fileForm.bank_reference" />
          <Button type="submit" variant="solid" :loading="busy" label="Mark as filed" />
        </form>
    </Dialog>
  </PageFrame>
</template>

<style scoped>
.cell { @apply h-7 py-0 leading-7 rounded-3 border border-transparent bg-transparent px-1.5 text-p-sm text-ink-gray-8 hover:border-outline-gray-2 focus:border-outline-gray-4 focus:bg-surface-gray-1 focus:outline-none disabled:hover:border-transparent; }
</style>
