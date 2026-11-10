<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, Dialog, LoadingIndicator, toast } from 'frappe-ui'
import { call, uploadFile } from '@/api'
import { money } from '@/format'

/** Same flow and rules as the wallet import: upload → review every row → Frappe Data Import. */
const open = defineModel<boolean>('open', { default: false })
const props = defineProps<{ mode: 'files' | 'csv' }>()
const emit = defineEmits<{ done: [] }>()

type Action = 'create' | 'update' | 'skip' | 'renumber'
interface Row {
  row: number; file?: string; invoice_number: string; original: string; action: Action; client: string
  client_label: string; new_client: boolean; wallet: string; errors: string[]; warnings: string[]; found?: string[]
  values: Record<string, string>; summary: { date: string; amount: number | null; currency: string; tax: string; total: number | null }
}
const step = ref<'upload' | 'review' | 'running' | 'done'>('upload')
const busy = ref(false)
const rows = ref<Row[]>([])
const unread = ref<{ file: string; message: string }[]>([])
const numbers = ref<Set<string>>(new Set())
const clients = ref<string[]>([])
const wallets = ref<string[]>([])
const result = ref<any>(null)
const input = ref<HTMLInputElement | null>(null)
const keptFiles = computed(() => rows.value.map((r) => r.values.source_file).filter(Boolean))

watch(open, (v, old) => {
  if (v) reset()
  else if (old && step.value === 'review' && keptFiles.value.length) discard()
})
function reset() { step.value = 'upload'; rows.value = []; unread.value = []; result.value = null; busy.value = false }
function discard() { call('supabill.api.invoice_import.discard_files', { file_urls: keptFiles.value }).catch(() => {}) }
function again() { if (keptFiles.value.length && step.value === 'review') discard(); reset() }

function load(r: any, names: Record<string, string> = {}) {
  // show the names the user chose (Frappe may rename duplicates when storing them)
  for (const x of r.rows) if (x.values?.source_file && names[x.values.source_file]) x.file = names[x.values.source_file]
  numbers.value = new Set(r.existing_numbers)
  clients.value = r.clients
  wallets.value = r.wallets
  rows.value = r.rows.map((x: any) => ({ ...x, original: x.invoice_number }))
  unread.value = r.unread || []
  if (!rows.value.length) { toast.error(unread.value.length ? 'None of the files could be read' : 'The file has no invoice rows'); return }
  step.value = 'review'
}
async function pick(e: Event) {
  const files = Array.from((e.target as HTMLInputElement).files ?? [])
  ;(e.target as HTMLInputElement).value = ''
  if (!files.length) return
  const ok = props.mode === 'csv' ? /\.csv$/i : /\.(pdf|docx)$/i
  const bad = files.filter((f) => !ok.test(f.name))
  if (bad.length) return toast.error(props.mode === 'csv' ? 'Choose a .csv file' : `Only PDF and Word (.docx) files: ${bad.map((f) => f.name).join(', ')}`)
  if (props.mode === 'csv' && files.length > 1) return toast.error('Choose one CSV file')
  if (files.length > 50) return toast.error('At most 50 files at a time')
  busy.value = true
  try {
    const urls: string[] = []
    const names: Record<string, string> = {}
    for (const f of files) { const u = await uploadFile(f); urls.push(u); names[u] = f.name }
    const res = props.mode === 'csv'
      ? await call('supabill.api.invoice_import.review_csv', { file_url: urls[0] })
      : await call('supabill.api.invoice_import.review_files', { file_urls: urls })
    for (const u of res.unread || []) { const hit = Object.entries(names).find(([url]) => url.endsWith('/' + u.file)); if (hit) u.file = hit[1] }
    load(res, names)
  } catch (err: any) { toast.error(err.message) } finally { busy.value = false }
}

const exists = (r: Row) => numbers.value.has(r.invoice_number.trim())
function setNumber(r: Row, v: string) {
  r.invoice_number = v
  if (!numbers.value.has(v.trim())) r.action = v.trim() === r.original ? 'create' : 'renumber'
  else if (r.action !== 'update' && r.action !== 'skip') r.action = 'skip'
}
function choices(r: Row): { value: Action; label: string }[] {
  return exists(r)
    ? [{ value: 'update', label: 'Update register fields' }, { value: 'skip', label: 'Skip' }, { value: 'renumber', label: 'Import with a new number' }]
    : [{ value: r.invoice_number.trim() === r.original ? 'create' : 'renumber', label: 'Create' }, { value: 'skip', label: 'Skip' }]
}
const NUMBER_ERR = /more than once|Invoice number/i
const WALLET_ERR = /wallet/i
function problem(r: Row): string {
  if (r.action === 'skip') return ''
  const n = r.invoice_number.trim()
  if (!n) return 'Type an invoice number'
  if (rows.value.some((o) => o !== r && o.action !== 'skip' && o.invoice_number.trim() === n)) return 'This number is used by another row'
  if (r.action === 'update') return exists(r) ? '' : 'No invoice with this number to update'
  if (exists(r)) return 'This number exists — choose Update, Skip or another number'
  if (!r.wallet) return 'Choose the wallet'
  if (!r.client && !r.client_label) return 'Choose a client'
  return r.errors.filter((e) => !NUMBER_ERR.test(e) && !WALLET_ERR.test(e))[0] || ''
}
const blocking = computed(() => rows.value.filter((r) => problem(r)).length)
const summary = computed(() => {
  const c = { create: 0, update: 0, skip: 0 }
  for (const r of rows.value) c[r.action === 'renumber' ? 'create' : r.action]++
  return c
})
function note(r: Row) {
  if (r.action === 'update') return 'Only register fields (wallet ref, received, charges, statuses) change; blank cells keep current values'
  return r.warnings[0] || (r.found ? `Found: ${r.found.join(', ')}` : '')
}

async function start() {
  busy.value = true
  try {
    const out = await call('supabill.api.invoice_import.run_import', {
      rows: rows.value.map((r) => ({ row: r.row, file: r.file, action: r.action, invoice_number: r.invoice_number.trim(),
        client: r.client, wallet: r.wallet, values: r.values })),
    })
    if (!out.data_import) { result.value = { created: 0, updated: 0, skipped: out.skipped, failed: [], invoices: [] }; step.value = 'done'; return }
    step.value = 'running'
    for (let i = 0; i < 200; i++) {
      const st = await call('supabill.api.invoice_import.import_status', { data_import: out.data_import }, { get: true })
      if (st.finished) { result.value = { ...st, skipped: st.skipped + out.skipped }; break }
      await new Promise((res) => setTimeout(res, 1500))
    }
    if (!result.value) throw new Error('The import is still running. Refresh the register in a minute.')
    step.value = 'done'
    emit('done')
  } catch (err: any) { toast.error(err.message); if (step.value === 'running') step.value = 'review' } finally { busy.value = false }
}
function template() { window.open('/api/method/supabill.api.invoice_import.download_template', '_blank') }
const title = computed(() => (props.mode === 'csv' ? 'Import invoices from CSV' : 'Import invoices from PDF / Word files'))
</script>

<template>
  <Dialog v-model:open="open" :title="title" size="7xl">
    <div v-if="step === 'upload'" class="grid gap-4 text-p-sm">
      <ol v-if="mode === 'csv'" class="list-decimal space-y-1 pl-5 text-ink-gray-7">
        <li>Download the template and fill one row per invoice. Keep the header row.</li>
        <li>Required: <b>Invoice Number, Invoice Date, Client, Currency, Amount Before Tax, Wallet</b>. Numeric dates are day first (15/04/2026). Tax Treatment: Export under LUT (default), IGST 18% or CGST + SGST 9+9.</li>
        <li>Upload it. You review every row and choose what happens to numbers that already exist before anything is saved.</li>
      </ol>
      <ol v-else class="list-decimal space-y-1 pl-5 text-ink-gray-7">
        <li>Choose one or more earlier invoices as <b>PDF</b> or <b>Word (.docx)</b> — one invoice per file.</li>
        <li>SupaBill finds the values by the words printed next to them (Invoice No, Invoice Date, Bill To, Total Due, Purpose Code, bank details…). No OCR or AI is used, so scanned (image) files can't be read.</li>
        <li>You review every invoice — number, client and wallet — before anything is saved. The original file is kept on the invoice.</li>
      </ol>
      <div class="flex flex-wrap gap-2">
        <Button v-if="mode === 'csv'" icon-left="lucide-download" label="Download CSV template" @click="template" />
        <Button variant="solid" icon-left="lucide-upload" :loading="busy" :label="mode === 'csv' ? 'Upload filled CSV' : 'Choose files'" @click="input?.click()" />
        <input ref="input" type="file" class="hidden" :multiple="mode === 'files'" :accept="mode === 'csv' ? '.csv,text/csv' : '.pdf,.docx,application/pdf'"
          :aria-label="mode === 'csv' ? 'CSV file' : 'Invoice files'" @change="pick" />
      </div>
      <p class="sb-note">Imported invoices keep their own numbers (your next number is unchanged), are locked like generated ones, and are added to the Excel workbook when Excel sync is on. The import runs through Frappe's Data Import.</p>
    </div>

    <div v-else-if="step === 'review'" class="grid gap-3 text-p-sm">
      <div class="flex flex-wrap items-center gap-2">
        {{ rows.length }} invoice{{ rows.length === 1 ? '' : 's' }}
        <span class="sb-pill sb-ok">{{ summary.create }} create</span>
        <span class="sb-pill sb-warn">{{ summary.update }} update</span>
        <span class="sb-pill sb-mute">{{ summary.skip }} skip</span>
        <span v-if="blocking" class="sb-pill sb-bad">{{ blocking }} to fix</span>
      </div>
      <div v-if="unread.length" class="rounded-4 border border-outline-red-2 bg-surface-red-1 p-2 text-xs text-ink-red-6">
        Not read: <span v-for="u in unread" :key="u.file" class="mr-2"><b>{{ u.file }}</b> — {{ u.message }}</span>
      </div>
      <div class="max-h-[58vh] overflow-auto rounded-4 border border-outline-gray-2">
        <table class="sb-table min-w-[1150px]">
          <thead class="sticky top-0 z-10 bg-surface-base"><tr>
            <th class="pl-3">{{ mode === 'csv' ? 'Row' : 'File' }}</th><th>Invoice no.</th><th>In SupaBill</th><th>What to do</th>
            <th>Date</th><th>Client</th><th>Wallet</th><th class="sb-num">Amount</th><th>Tax</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.row" :class="{ 'opacity-60': r.action === 'skip' }">
              <td class="max-w-40 truncate pl-3 text-ink-gray-5" :title="r.file || ''">{{ r.file || r.row }}</td>
              <td><input class="cell w-40" :value="r.invoice_number" :aria-label="`Invoice number, ${r.file || 'row ' + r.row}`" @input="(e: any) => setNumber(r, e.target.value)" /></td>
              <td><span class="sb-pill" :class="exists(r) ? 'sb-warn' : 'sb-ok'">{{ exists(r) ? 'Exists' : 'New' }}</span></td>
              <td><select class="cell" :value="r.action" :aria-label="`Action, ${r.file || 'row ' + r.row}`" @change="(e: any) => (r.action = e.target.value)">
                <option v-for="c in choices(r)" :key="c.value" :value="c.value">{{ c.label }}</option></select></td>
              <td class="whitespace-nowrap">{{ r.summary.date }}</td>
              <td>
                <select class="cell max-w-52" :value="r.client" :disabled="r.action === 'update' || r.action === 'skip'" :aria-label="`Client, ${r.file || 'row ' + r.row}`" @change="(e: any) => (r.client = e.target.value)">
                  <option v-if="r.new_client && r.client_label" value="">Create new: {{ r.client_label }}</option>
                  <option v-else-if="!r.client" value="" disabled>Choose…</option>
                  <option v-for="c in clients" :key="c" :value="c">{{ c }}</option>
                </select>
              </td>
              <td>
                <select class="cell" :value="r.wallet" :disabled="r.action === 'update' || r.action === 'skip'" :aria-label="`Wallet, ${r.file || 'row ' + r.row}`" @change="(e: any) => (r.wallet = e.target.value)">
                  <option value="" disabled>Choose…</option>
                  <option v-for="w in wallets" :key="w" :value="w">{{ w }}</option>
                </select>
              </td>
              <td class="sb-num whitespace-nowrap">{{ r.summary.amount ? money(r.summary.amount, r.summary.currency || 'USD') : '—' }}</td>
              <td class="whitespace-nowrap text-xs">{{ r.summary.tax || '—' }}</td>
              <td class="max-w-80 text-xs" :class="problem(r) ? 'text-ink-red-5' : r.warnings.length && r.action !== 'update' ? 'text-ink-amber-6' : 'text-ink-gray-5'">{{ problem(r) || note(r) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex justify-end gap-2">
        <Button :label="mode === 'csv' ? 'Choose another file' : 'Choose other files'" @click="again" />
        <Button variant="solid" :loading="busy" :disabled="!!blocking" :label="`Import ${summary.create + summary.update} invoice${summary.create + summary.update === 1 ? '' : 's'}`" @click="start" />
      </div>
    </div>

    <div v-else-if="step === 'running'" class="flex items-center gap-3 py-10 text-p-sm"><LoadingIndicator class="size-5" /> Importing through Data Import…</div>

    <div v-else class="grid gap-3 text-p-sm">
      <div class="flex flex-wrap gap-2">
        <span class="sb-pill sb-ok">{{ result.created }} created</span>
        <span class="sb-pill sb-warn">{{ result.updated }} updated</span>
        <span class="sb-pill sb-mute">{{ result.skipped }} skipped</span>
        <span v-if="result.failed.length" class="sb-pill sb-bad">{{ result.failed.length }} failed</span>
      </div>
      <ul v-if="result.invoices.length" class="max-h-48 list-disc overflow-auto pl-5"><li v-for="w in result.invoices" :key="w.invoice_number">{{ w.invoice_number }} — {{ w.result }}</li></ul>
      <ul v-if="result.failed.length" class="list-disc pl-5 text-ink-red-6"><li v-for="(f, i) in result.failed" :key="i">{{ f.message }}</li></ul>
      <div class="flex justify-end gap-2"><Button label="Import more" @click="reset" /><Button variant="solid" label="Done" @click="open = false" /></div>
    </div>
  </Dialog>
</template>

<style scoped>
.cell { @apply h-7 py-0 leading-7 rounded-3 border border-outline-gray-2 bg-transparent px-1.5 text-p-sm text-ink-gray-8 focus:border-outline-gray-4 focus:outline-none disabled:opacity-50; }
</style>
