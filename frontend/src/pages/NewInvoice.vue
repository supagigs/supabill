<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Button, FormControl, LoadingIndicator, toast } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import InvoicePaper from '@/components/InvoicePaper.vue'
import { call, newRequestId } from '@/api'
import { money, inr, fmtDate, today } from '@/format'
import type { Boot, Client, Item, Preview } from '@/types'
import { session } from '@/session'

const boot = ref<Boot | null>(null)
const loadError = ref('')
const preview = ref<Preview | null>(null)
const previewing = ref(false)
const creating = ref(false)
const created = ref<null | { name: string; client_name: string; grand_total: number; currency: string; amount_inr: number }>(null)
const tab = ref<'invoice' | 'row'>('invoice')
const requestId = ref(newRequestId())
const descEdited = ref(false)
const regEdited = ref(false)

const TERMS = [0, 7, 15, 21, 30, 45].map((d) => ({ label: d ? `Net ${d}` : 'Due on receipt', value: d }))
const METHODS = ['ACH bank transfer', 'Wire transfer (SWIFT)', 'Upwork', 'NEFT / RTGS / UPI']
const CURRENCIES = ['USD', 'INR', 'EUR', 'GBP', 'AUD', 'CAD']

const f = reactive<Record<string, any>>({})
const items = ref<Item[]>([])

function blankForm() {
  Object.assign(f, {
    client: '', client_name: '', billing_address: '', client_country: '', attention: '', client_email: '', project: '',
    milestone: '', billing_period: '', invoice_date: today(), payment_terms_days: 21, currency: 'USD', wallet: '',
    wallet_name_other: '', payment_method: 'ACH bank transfer', tax_treatment: 'Export under LUT', purpose_code: '',
    country_of_supply: 'India', cbic_rate: null, cbic_rate_source: 'Auto', notes: '', wallet_reference: '',
    invoice_status: 'Raised', upwork_invoice: '', upwork_account_holder: '', register_description: '',
  })
}
blankForm()

const s = computed(() => boot.value?.settings || {})
const wallet = computed(() => boot.value?.wallets.find((w) => w.name === f.wallet))
const lut = computed(() => f.tax_treatment === 'Export under LUT')
const lutNote = () => (s.value.lut_note || '').replace('{ARN}', s.value.lut_arn || '')
const favPurpose = computed(() => (boot.value?.purpose_codes || []).filter((p) => p.is_favourite))
const sacCodes = computed(() => (boot.value?.tax_codes || []).filter((c) => c.code_type === 'SAC'))
const hsnCodes = computed(() => (boot.value?.tax_codes || []).filter((c) => c.code_type === 'HSN'))

function nextMilestone(m?: string) {
  return (m || '').replace(/(\d+)\s+of\s+(\d+)/i, (_x, a, b) => `${Math.min(+a + 1, +b)} of ${b}`)
}
const shortMilestone = () => (f.milestone || '').replace(/\s+of\s+\d+/i, '')
const autoDesc = () => [f.project, shortMilestone()].filter(Boolean).join(' – ') + (f.billing_period ? ` (${f.billing_period})` : '')
const lineDesc = (i: number) => (i === 0 && !descEdited.value ? autoDesc() : items.value[i]?.description || '')

function selectClient(name: string, repeat = false) {
  const c = boot.value?.clients.find((x) => x.name === name) as Client | undefined
  if (!c) return
  created.value = null
  requestId.value = newRequestId()
  Object.assign(f, {
    client: c.name, client_name: c.client_name, billing_address: c.address || '', client_country: c.country || '',
    attention: c.contact_person || '', client_email: c.email || '', project: c.project || '',
    currency: c.currency || s.value.default_currency || 'USD', payment_terms_days: c.payment_terms_days ?? s.value.default_terms_days ?? 21,
    wallet: c.wallet || '', payment_method: c.payment_method || 'ACH bank transfer', tax_treatment: c.tax_treatment || 'Export under LUT',
    purpose_code: c.purpose_code || s.value.default_purpose_code || '', milestone: repeat ? c.last_milestone || '' : nextMilestone(c.last_milestone),
    billing_period: repeat ? c.last_billing_period || '' : '', cbic_rate: null, cbic_rate_source: 'Auto',
    wallet_reference: '', upwork_invoice: '', upwork_account_holder: '', wallet_name_other: '',
    country_of_supply: s.value.country_of_supply || 'India',
  })
  f.notes = f.tax_treatment === 'Export under LUT' ? lutNote() : ''
  items.value = [{ description: '', sac_code: c.sac_code || s.value.default_sac || '', hsn_code: c.hsn_code || '', qty: 1, rate: c.last_amount || 0 }]
  descEdited.value = false
  regEdited.value = false
  if (repeat) toast.success(`Copied the last invoice for ${c.client_name}`)
}

function setTax(t: string) {
  f.tax_treatment = t
  f.notes = t === 'Export under LUT' ? lutNote() : ''
}
function addItem() {
  items.value.push({ description: '', sac_code: items.value[0]?.sac_code || '', hsn_code: items.value[0]?.hsn_code || '', qty: 1, rate: 0 })
}
function onDescInput(i: number, v: string) {
  items.value[i].description = v
  if (i === 0) descEdited.value = !!v
}

watch(
  () => [f.project, f.milestone],
  () => {
    if (!regEdited.value) f.register_description = [String(f.project || '').split(' ').slice(0, 3).join(' '), shortMilestone()].filter(Boolean).join(' – ')
  },
)

function payload() {
  return {
    ...f,
    payment_terms_days: Number(f.payment_terms_days),
    cbic_rate: f.cbic_rate_source === 'Manual' ? Number(f.cbic_rate) : null,
    items: items.value.map((it, i) => ({ ...it, description: lineDesc(i), qty: Number(it.qty) || 0, rate: Number(it.rate) || 0 })),
  }
}

let timer: number | undefined
let seq = 0
function schedulePreview() {
  if (!boot.value || !f.client) return
  window.clearTimeout(timer)
  timer = window.setTimeout(runPreview, 250)
}
async function runPreview() {
  const mine = ++seq
  previewing.value = true
  try {
    const p = await call<Preview>('supabill.api.invoice.preview', { payload: payload() })
    if (mine !== seq) return
    preview.value = p
    if (f.cbic_rate_source !== 'Manual') f.cbic_rate = p.cbic_rate
  } catch (e: any) {
    if (mine === seq) toast.error(e.message)
  } finally {
    if (mine === seq) previewing.value = false
  }
}
watch([() => ({ ...f, cbic_rate: f.cbic_rate_source === 'Manual' ? f.cbic_rate : null }), items], schedulePreview, { deep: true })

const errors = computed(() => (preview.value?.readiness || []).filter((r) => r.level === 'error'))
const warnings = computed(() => (preview.value?.readiness || []).filter((r) => r.level === 'warning'))
const canGenerate = computed(() => !!f.client && !!preview.value && !errors.value.length && !previewing.value && !creating.value && !created.value)

async function generate() {
  if (!canGenerate.value) {
    if (errors.value.length) toast.error('Fix first: ' + errors.value[0].message)
    return
  }
  creating.value = true
  try {
    const r = await call('supabill.api.invoice.create_invoice', { payload: payload(), request_id: requestId.value })
    created.value = r
    toast.success(`${r.name} generated and added to the register`)
    await loadBoot(false)
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    creating.value = false
  }
}
function startNext() {
  const c = f.client
  created.value = null
  selectClient(c)
}
function download(fmt: 'pdf' | 'docx') {
  if (!created.value) return
  window.open(`/api/method/supabill.api.output.download?name=${encodeURIComponent(created.value.name)}&fmt=${fmt}`, '_blank')
}

async function loadBoot(pickFirst = true) {
  try {
    boot.value = await call<Boot>('supabill.api.invoice.bootstrap', {}, { get: true })
    loadError.value = ''
    if (pickFirst && boot.value.clients.length && !f.client) selectClient(boot.value.clients[0].name)
  } catch (e: any) {
    loadError.value = e.message
  }
}

function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    generate()
  }
}
onMounted(() => {
  loadBoot()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const regRow = computed(() => [
  ['Invoice No', preview.value?.next_invoice], ['Upwork Invoice', f.upwork_invoice], ['Upwork Holder', f.upwork_account_holder],
  ['Wallet Ref', f.wallet_reference], ['Invoice Date', fmtDate(f.invoice_date)], ['Month', '=MONTH(F…)'], ['Client', f.client_name],
  ['Description', f.register_description], ['Wallet', f.wallet === 'Others' && f.wallet_name_other ? f.wallet_name_other : f.wallet],
  ['GST Return', preview.value?.gst_return_period], ['Currency', f.currency], ['Amount', preview.value?.grand_total?.toFixed(2)],
  ['CBIC Rate', f.cbic_rate], ['Amount INR', '=M×N'], ['Received', ''], ['Forex Gain', '=P−O'], ['Payment Status', 'Pending'], ['Invoice Status', f.invoice_status],
])
</script>

<template>
  <PageFrame title="New invoice" subtitle="Pick a client, enter the amount, generate">
    <template #actions>
      <Button v-if="created" label="PDF" icon-left="lucide-download" @click="download('pdf')" />
      <Button v-if="created" label="DOCX" icon-left="lucide-file-text" @click="download('docx')" />
      <Button variant="solid" :loading="creating" :disabled="!canGenerate" @click="generate">
        Generate &amp; add to register <kbd class="ml-2 hidden rounded-2 border border-current px-1 text-[10px] opacity-70 md:inline">Ctrl ↵</kbd>
      </Button>
    </template>

    <div v-if="loadError" class="rounded-4 bg-surface-red-1 p-4 text-p-sm text-ink-red-4">
      Couldn’t load SupaBill data: {{ loadError }} <Button class="ml-2" label="Retry" @click="loadBoot()" />
    </div>
    <div v-else-if="!boot" class="flex justify-center py-20 text-ink-gray-5"><LoadingIndicator class="size-6" /></div>

    <div v-else-if="!boot.clients.length" class="rounded-6 border border-dashed border-outline-gray-2 px-6 py-14 text-center">
      <p class="text-base font-semibold text-ink-gray-8">Add your first client</p>
      <p class="mt-1 text-p-sm text-ink-gray-5">Clients hold the address, wallet, terms and codes that fill each invoice.</p>
      <Button class="mt-4" variant="solid" label="Add client" :route="{ name: 'Clients', query: { new: '1' } }" />
    </div>

    <div v-else class="grid gap-5 lg:grid-cols-[minmax(340px,430px)_1fr]">
      <div class="flex flex-col gap-3">
        <section class="card">
          <div class="sect">Client <RouterLink class="link" :to="{ name: 'Clients', query: { new: '1' } }">+ New client</RouterLink></div>
          <div class="flex flex-wrap gap-1.5">
            <button v-for="c in boot.clients" :key="c.name" type="button" class="chip" :class="{ on: c.name === f.client }" @click="selectClient(c.name)">{{ c.client_name }}</button>
          </div>
        </section>

        <section class="card">
          <div class="sect">This invoice <button type="button" class="link" @click="selectClient(f.client, true)">↺ Repeat last for this client</button></div>
          <div class="grid grid-cols-2 gap-2.5">
            <FormControl class="col-span-2" label="Milestone / billing line" v-model="f.milestone" />
            <FormControl label="Billing period" v-model="f.billing_period" placeholder="e.g. 1 Nov – 30 Nov 2026" />
            <FormControl type="date" label="Invoice date" v-model="f.invoice_date" />
            <FormControl type="select" label="Payment terms" v-model="f.payment_terms_days" :options="TERMS" />
            <div><div class="lbl">Due date <span class="auto">auto</span></div><div class="ro">{{ fmtDate(preview?.due_date) || '—' }}</div></div>
            <FormControl type="select" label="Receive via (wallet)" v-model="f.wallet" :options="boot.wallets.map((w) => ({ label: w.name + (w.complete ? '' : ' · details missing'), value: w.name }))" />
            <FormControl label="Wallet name (“Others” only)" v-model="f.wallet_name_other" :disabled="f.wallet !== 'Others'" />
            <div class="col-span-2">
              <FormControl label="Purpose code (RBI)" v-model="f.purpose_code" list="sb-purpose" />
              <datalist id="sb-purpose"><option v-for="p in boot.purpose_codes" :key="p.code" :value="p.code">{{ p.is_favourite ? '★ ' : '' }}{{ p.description }}</option></datalist>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <button v-for="p in favPurpose" :key="p.code" type="button" class="chip sm" :class="{ on: f.purpose_code === p.code }" :title="p.description" @click="f.purpose_code = p.code">★ {{ p.code }}</button>
              </div>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="sect">Items <button type="button" class="link" @click="addItem">+ Add line</button></div>
          <div v-for="(it, i) in items" :key="i" class="relative mb-2 rounded-4 border border-outline-gray-1 p-2.5">
            <button v-if="items.length > 1" type="button" class="absolute right-1.5 top-1 text-ink-gray-5" :aria-label="`Remove line ${i + 1}`" @click="items.splice(i, 1)">✕</button>
            <FormControl type="textarea" :rows="2" :model-value="it.description" :placeholder="i === 0 ? autoDesc() || 'Project – milestone (period)' : 'Description'" @update:model-value="(v: string) => onDescInput(i, v)" />
            <div class="mt-1.5 grid grid-cols-[1.3fr_.6fr_1fr_1fr] gap-1.5">
              <FormControl type="number" v-model="it.rate" placeholder="Unit price" aria-label="Unit price" />
              <FormControl type="number" v-model="it.qty" aria-label="Quantity" />
              <FormControl v-model="it.sac_code" placeholder="SAC" list="sb-sac" aria-label="SAC code" />
              <FormControl v-model="it.hsn_code" placeholder="HSN" list="sb-hsn" aria-label="HSN code" />
            </div>
          </div>
          <datalist id="sb-sac"><option v-for="c in sacCodes" :key="c.code" :value="c.code">{{ c.is_favourite ? '★ ' : '' }}{{ c.description }}</option></datalist>
          <datalist id="sb-hsn"><option v-for="c in hsnCodes" :key="c.code" :value="c.code">{{ c.is_favourite ? '★ ' : '' }}{{ c.description }}</option></datalist>
          <div class="lbl mt-3">Tax treatment</div>
          <div class="seg" role="radiogroup" aria-label="Tax treatment">
            <button v-for="t in boot.tax_treatments" :key="t" type="button" role="radio" :aria-checked="f.tax_treatment === t" :class="{ on: f.tax_treatment === t }" @click="setTax(t)">
              {{ t === 'Export under LUT' ? 'Export · LUT 0%' : t === 'IGST 18%' ? 'IGST 18%' : 'CGST+SGST 9+9' }}
            </button>
          </div>
          <div class="mt-2.5 rounded-4 bg-surface-gray-2 px-3 py-2.5 text-p-sm">
            <div class="flex justify-between"><span>Sub total</span><span>{{ money(preview?.subtotal, f.currency) }}</span></div>
            <div class="flex justify-between text-ink-gray-6"><span>{{ lut ? 'Tax (export under LUT)' : f.tax_treatment }}</span><span>{{ money(preview?.tax_total, f.currency) }}</span></div>
            <div class="mt-1 flex justify-between border-t border-outline-gray-2 pt-1.5 text-base font-semibold"><span>Total due</span><span>{{ money(preview?.grand_total, f.currency) }} {{ f.currency }}</span></div>
            <div v-if="f.currency !== 'INR'" class="flex justify-between text-ink-gray-5"><span>≈ INR at CBIC {{ f.cbic_rate || '—' }}</span><span>{{ f.cbic_rate ? inr(preview?.amount_inr) : 'rate needed' }}</span></div>
          </div>
        </section>

        <details class="card !p-0">
          <summary class="summ">Register fields <span>CBIC {{ f.cbic_rate || '—' }} · {{ preview?.gst_return_period }}</span></summary>
          <div class="grid grid-cols-2 gap-2.5 px-4 pb-4">
            <div>
              <FormControl type="number" label="CBIC export rate" :model-value="f.cbic_rate" :disabled="f.currency === 'INR'" @update:model-value="(v: any) => { f.cbic_rate = v; f.cbic_rate_source = 'Manual' }" />
              <div class="mt-1 text-xs" :class="f.cbic_rate_source === 'Manual' ? 'text-ink-amber-4' : 'text-ink-gray-5'">
                <template v-if="f.currency === 'INR'">Not needed for INR</template>
                <template v-else-if="f.cbic_rate_source === 'Manual'">Manual · <button type="button" class="link !p-0" @click="f.cbic_rate_source = 'Auto'">use notified rate</button></template>
                <template v-else-if="preview?.cbic_rate_effective_from">Auto · notified {{ fmtDate(preview.cbic_rate_effective_from) }}</template>
                <template v-else-if="preview && !preview.cbic_rate"><span class="text-ink-red-4">No rate for this date — add one in Settings</span></template>
              </div>
            </div>
            <div><div class="lbl">GST return <span class="auto">auto</span></div><div class="ro">{{ preview?.gst_return_period || '—' }}</div></div>
            <FormControl label="Wallet ref. no." v-model="f.wallet_reference" placeholder="can be added later" />
            <FormControl type="select" label="Invoice status" v-model="f.invoice_status" :options="['Raised', 'Sent']" />
            <template v-if="wallet?.is_upwork">
              <FormControl label="Upwork invoice" v-model="f.upwork_invoice" />
              <FormControl label="Upwork account holder" v-model="f.upwork_account_holder" />
            </template>
            <FormControl class="col-span-2" label="Register description" :model-value="f.register_description" @update:model-value="(v: string) => { f.register_description = v; regEdited = true }" />
          </div>
        </details>

        <details class="card !p-0">
          <summary class="summ">Bill-to details <span>{{ [f.attention, f.client_country].filter(Boolean).join(' · ') }}</span></summary>
          <div class="grid grid-cols-2 gap-2.5 px-4 pb-4">
            <FormControl class="col-span-2" label="Client name" v-model="f.client_name" />
            <FormControl class="col-span-2" type="textarea" label="Address" v-model="f.billing_address" />
            <FormControl label="Country" v-model="f.client_country" />
            <FormControl label="Attention" v-model="f.attention" />
            <FormControl class="col-span-2" label="Email" v-model="f.client_email" />
            <FormControl class="col-span-2" label="Project" v-model="f.project" />
            <FormControl class="col-span-2" type="select" label="Payment method" v-model="f.payment_method" :options="METHODS" />
          </div>
        </details>

        <details class="card !p-0">
          <summary class="summ">Invoice settings <span>{{ preview?.next_invoice }} · {{ f.currency }}</span></summary>
          <div class="grid grid-cols-2 gap-2.5 px-4 pb-4">
            <div><div class="lbl">Invoice no. <span class="auto">auto</span></div><div class="ro">{{ preview?.next_invoice }}</div></div>
            <FormControl type="select" label="Currency" v-model="f.currency" :options="CURRENCIES" />
            <FormControl class="col-span-2" label="Country of supply" v-model="f.country_of_supply" />
            <FormControl class="col-span-2" type="textarea" label="Notes" v-model="f.notes" :rows="4" />
          </div>
        </details>
      </div>

      <div class="min-w-0">
        <section v-if="created" class="card mb-3 !border-outline-green-2 !bg-surface-green-1" role="status">
          <div class="sect !text-ink-green-4">✓ Invoice {{ created.name }} generated</div>
          <p class="mb-3 text-p-sm text-ink-gray-6">{{ money(created.grand_total, created.currency) }} for {{ created.client_name }} · added to the register<span v-if="s.excel_enabled"> and queued for Excel</span>.</p>
          <div class="flex flex-wrap gap-2">
            <Button label="Download PDF" icon-left="lucide-download" @click="download('pdf')" />
            <Button label="Download DOCX" icon-left="lucide-file-text" @click="download('docx')" />
            <Button label="Open in register" :route="{ name: 'Register', query: { q: created.name } }" />
            <Button variant="solid" label="Start next invoice" @click="startNext" />
          </div>
        </section>
        <section v-else class="card mb-3" aria-live="polite">
          <div class="sect">
            <span v-if="!preview" class="text-ink-gray-5">Checking…</span>
            <span v-else-if="errors.length" class="text-ink-red-4">Fix {{ errors.length }} item{{ errors.length > 1 ? 's' : '' }} before generating</span>
            <span v-else class="text-ink-green-4">✓ Ready to generate</span>
            <span class="normal-case tracking-normal">{{ warnings.length ? warnings.length + ' optional' : '' }} <LoadingIndicator v-if="previewing" class="ml-1 inline size-3" /></span>
          </div>
          <ul class="flex flex-col gap-1 text-p-sm">
            <li v-for="e in errors" :key="e.message" class="flex gap-2 text-ink-red-4"><span aria-hidden="true">✕</span>{{ e.message }}</li>
            <li v-for="w in warnings" :key="w.message" class="flex gap-2 text-ink-gray-6"><span class="text-ink-amber-4" aria-hidden="true">!</span>{{ w.message }}</li>
          </ul>
        </section>

        <div class="mb-3 flex gap-1">
          <button type="button" class="chip" :class="{ on: tab === 'invoice' }" @click="tab = 'invoice'">Invoice</button>
          <button type="button" class="chip" :class="{ on: tab === 'row' }" @click="tab = 'row'">Register row</button>
        </div>
        <InvoicePaper v-if="tab === 'invoice'" :s="s" :f="f" :items="items" :line-desc="lineDesc" :totals="preview" :invoice-no="created?.name || preview?.next_invoice || ''" :due-date="preview?.due_date || ''" :bank="wallet?.details || []" />
        <section v-else class="card overflow-x-auto">
          <div class="sect">Row appended to sheet “{{ s.worksheet_name || 'Sheet1' }}”</div>
          <table class="w-full min-w-[640px] border-collapse text-xs">
            <tbody>
              <tr v-for="[k, v] in regRow" :key="k" class="border-b border-outline-gray-1">
                <th class="w-40 py-1.5 pr-3 text-left font-medium text-ink-gray-5">{{ k }}</th>
                <td class="py-1.5" :class="{ 'font-mono text-ink-gray-5': String(v || '').startsWith('=') }">{{ v }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-2 text-xs text-ink-gray-5">Formula cells are written as Excel formulas. Received, charges and status are filled in the Sales register when money arrives.</p>
        </section>
        <p v-if="!session.isManager" class="mt-3 text-xs text-ink-gray-5">Only managers can cancel an invoice after it is generated.</p>
      </div>
    </div>
  </PageFrame>
</template>

<style scoped>
.card { @apply rounded-6 border border-outline-gray-2 bg-surface-base p-4; }
.sect { @apply mb-2.5 flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wider text-ink-gray-5; }
.link { @apply text-xs font-medium normal-case tracking-normal text-ink-blue-5 hover:underline; }
.chip { @apply rounded-full border border-outline-gray-2 bg-surface-base px-3 py-1.5 text-p-sm text-ink-gray-8 hover:bg-surface-gray-2; }
.chip.sm { @apply px-2.5 py-0.5 text-xs; }
.chip.on { @apply border-outline-gray-4 bg-surface-gray-3 font-medium text-ink-gray-9; }
.lbl { @apply mb-1.5 text-xs text-ink-gray-5; }
.auto { @apply ml-1 text-[10.5px] font-semibold text-ink-green-4; }
.ro { @apply flex h-7 items-center rounded-2 bg-surface-gray-2 px-2 text-base text-ink-gray-7; }
.seg { @apply flex gap-1 rounded-4 bg-surface-gray-2 p-1; }
.seg button { @apply flex-1 rounded-3 px-2 py-1.5 text-xs text-ink-gray-6; }
.seg button.on { @apply bg-surface-base font-semibold text-ink-gray-9 shadow-sm; }
.summ { @apply flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-p-sm font-semibold text-ink-gray-8; }
.summ span { @apply ml-auto truncate text-xs font-normal text-ink-gray-5; }
.summ::-webkit-details-marker { display: none; }
</style>
