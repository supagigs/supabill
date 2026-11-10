<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Button, FormControl, LoadingIndicator, toast } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'
import { fmtDate } from '@/format'

const s = reactive<Record<string, any>>({})
const loaded = ref(false)
const saving = ref(false)
const secrets = reactive<Record<string, string>>({ ms_client_secret: '', allratestoday_api_key: '' })
const clear = ref<string[]>([])
const codes = ref<{ tax_codes: any[]; purpose_codes: any[] }>({ tax_codes: [], purpose_codes: [] })
const rates = ref<any[]>([])
const newCode = reactive({ kind: 'tax', code_type: 'SAC', code: '', description: '' })
const newRate = reactive({ effective_from: '', currency: 'USD', export_rate: '', import_rate: '' })
const busy = reactive({ cbic: false, excelTest: false, excelSync: false })

const preview = computed(() => `${s.invoice_prefix || ''}${String(s.next_invoice_number || 1).padStart(Math.max(+s.number_digits || 1, 1), '0')}`)
const CURR = ['USD', 'INR', 'EUR', 'GBP', 'AUD', 'CAD']
const TERMS = [0, 7, 15, 21, 30, 45].map((d) => ({ label: d ? `Net ${d}` : 'Due on receipt', value: d }))

async function load() {
  const [st, c, r] = await Promise.all([
    call('supabill.api.setup.get_settings', {}, { get: true }),
    call('supabill.api.setup.list_codes', {}, { get: true }),
    call('supabill.api.setup.list_cbic_rates', {}, { get: true }),
  ])
  Object.assign(s, st)
  codes.value = c
  rates.value = r
  loaded.value = true
}
async function save() {
  saving.value = true
  try {
    const out = await call('supabill.api.setup.save_settings', { values: s, secrets, clear_secrets: clear.value })
    Object.assign(s, out)
    secrets.ms_client_secret = ''
    secrets.allratestoday_api_key = ''
    clear.value = []
    toast.success('Settings saved')
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
async function addCode() {
  if (!newCode.code.trim()) return toast.error('Enter a code')
  try {
    codes.value = await call('supabill.api.setup.save_code', { kind: newCode.kind, code: newCode.code.trim(), description: newCode.description, code_type: newCode.code_type, is_favourite: 1 })
    toast.success(`${newCode.code} added as a favourite`)
    newCode.code = newCode.description = ''
  } catch (e: any) { toast.error(e.message) }
}
async function star(kind: string, name: string) {
  codes.value = await call('supabill.api.setup.toggle_favourite', { kind, name })
}
async function delCode(kind: string, name: string) {
  try { codes.value = await call('supabill.api.setup.delete_code', { kind, name }) } catch (e: any) { toast.error(e.message) }
}
async function addRate() {
  if (!newRate.effective_from || !+newRate.export_rate) return toast.error('Enter the effective date and export rate')
  try {
    rates.value = await call('supabill.api.setup.save_cbic_rate', { ...newRate, export_rate: +newRate.export_rate, import_rate: +newRate.import_rate || null })
    toast.success('Rate saved')
    newRate.export_rate = newRate.import_rate = ''
  } catch (e: any) { toast.error(e.message) }
}
async function delRate(name: string) {
  rates.value = await call('supabill.api.setup.delete_cbic_rate', { name })
}
async function fetchCbic() {
  busy.cbic = true
  try {
    const r = await call('supabill.api.integrations.sync_cbic_now')
    toast.success(r.message)
    await load()
  } catch (e: any) { toast.error(e.message); await load() } finally { busy.cbic = false }
}
async function excelTest() {
  busy.excelTest = true
  try { toast.success((await call('supabill.api.integrations.excel_test')).message) } catch (e: any) { toast.error(e.message) } finally { busy.excelTest = false }
}
async function excelSync() {
  busy.excelSync = true
  try { toast.success((await call('supabill.api.integrations.excel_sync_now')).message); await load() } catch (e: any) { toast.error(e.message) } finally { busy.excelSync = false }
}
function secretState(k: string) {
  if (clear.value.includes(k)) return 'Will be removed when you save'
  return s['has_' + k] ? 'Saved on the server — type a new value to replace it' : 'Not set'
}
onMounted(load)
</script>

<template>
  <PageFrame title="Settings" subtitle="Company, numbering, defaults, codes and integrations">
    <template #actions><Button variant="solid" :loading="saving" label="Save settings" @click="save" /></template>
    <div v-if="!loaded" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <form v-else class="flex max-w-4xl flex-col gap-4" @submit.prevent="save">
      <section class="sb-card">
        <h2 class="text-base font-semibold">Company</h2><p class="sb-note mb-3">Printed in the header and FROM block of every invoice.</p>
        <div class="grid gap-2.5 sm:grid-cols-2">
          <FormControl class="sm:col-span-2" label="Legal name" v-model="s.legal_name" required />
          <FormControl label="Display name" v-model="s.display_name" /><FormControl label="Email" v-model="s.company_email" />
          <FormControl class="sm:col-span-2" type="textarea" label="Address" v-model="s.company_address" />
          <FormControl label="Contact" v-model="s.company_phone" /><FormControl label="GSTIN" v-model="s.gstin" />
          <FormControl label="PAN" v-model="s.pan" /><FormControl label="IEC" v-model="s.iec" />
        </div>
      </section>
      <section class="sb-card">
        <h2 class="text-base font-semibold">Invoice numbering</h2><p class="sb-note mb-3">The next number is taken under a lock, so two people never get the same one.</p>
        <div class="grid gap-2.5 sm:grid-cols-3">
          <FormControl label="Prefix" v-model="s.invoice_prefix" required />
          <FormControl type="number" label="Next number" v-model="s.next_invoice_number" />
          <FormControl type="number" label="Digits" v-model="s.number_digits" />
        </div>
        <div class="mt-2 inline-block rounded-4 bg-surface-gray-2 px-2.5 py-1 font-mono text-xs text-ink-gray-7">Next invoice: {{ preview }}</div>
      </section>
      <section class="sb-card">
        <h2 class="text-base font-semibold">Invoice defaults</h2><p class="sb-note mb-3">Used for new clients and invoices.</p>
        <div class="grid gap-2.5 sm:grid-cols-2">
          <FormControl type="select" label="Default currency" v-model="s.default_currency" :options="CURR" />
          <FormControl type="select" label="Default terms" v-model="s.default_terms_days" :options="TERMS" />
          <FormControl label="Default SAC" v-model="s.default_sac" /><FormControl label="Default HSN" v-model="s.default_hsn" />
          <FormControl type="select" label="Default purpose code" v-model="s.default_purpose_code" :options="[{ label: '—', value: '' }, ...codes.purpose_codes.map((p) => ({ label: p.code + ' · ' + p.description, value: p.code }))]" />
          <FormControl label="Country of supply" v-model="s.country_of_supply" />
          <FormControl type="number" label="Fallback CBIC rate" v-model="s.default_cbic_rate" description="Only used when no notified rate covers an invoice date" />
          <div class="sb-note self-end pb-1">PDF engine: <b>{{ s.pdf_engine }}</b></div>
        </div>
      </section>
      <section class="sb-card">
        <h2 class="text-base font-semibold">Export / LUT</h2><p class="sb-note mb-3">Update the ARN when you renew the LUT each financial year. {ARN} in the note is replaced automatically.</p>
        <div class="grid gap-2.5"><FormControl label="LUT ARN" v-model="s.lut_arn" /><FormControl type="textarea" label="LUT note" v-model="s.lut_note" /></div>
      </section>
      <section class="sb-card">
        <h2 class="text-base font-semibold">AD bank &amp; signatory</h2><p class="sb-note mb-3">All wallets settle into this bank. Printed on the EDF (Sections 1 and 4).</p>
        <div class="grid gap-2.5 sm:grid-cols-2">
          <FormControl label="AD bank name" v-model="s.ad_bank_name" /><FormControl label="AD code" v-model="s.ad_code" />
          <FormControl class="sm:col-span-2" label="Branch address" v-model="s.ad_branch_address" />
          <FormControl label="Authorised signatory" v-model="s.signatory_name" /><FormControl label="Designation" v-model="s.signatory_designation" />
          <FormControl label="Place" v-model="s.signatory_place" />
          <FormControl type="number" label="Realisation period (months)" v-model="s.realisation_months" description="RBI period for realising export proceeds" />
        </div>
      </section>

      <section class="sb-card">
        <h2 class="text-base font-semibold">SAC &amp; HSN codes</h2><p class="sb-note mb-3">Starred codes appear first when filling a line item.</p>
        <div v-for="t in ['SAC', 'HSN']" :key="t" class="mb-2">
          <div class="sb-lbl font-semibold">{{ t }}</div>
          <div v-for="c in codes.tax_codes.filter((x) => x.code_type === t)" :key="c.name" class="flex items-center gap-3 border-b border-outline-gray-1 py-1.5 text-p-sm">
            <button type="button" class="text-lg" :class="c.is_favourite ? 'text-ink-amber-5' : 'text-ink-gray-4'" :aria-label="(c.is_favourite ? 'Unstar ' : 'Star ') + c.code" @click="star('tax', c.name)">{{ c.is_favourite ? '★' : '☆' }}</button>
            <b class="w-20">{{ c.code }}</b><span class="flex-1 text-ink-gray-6">{{ c.description }}</span>
            <Button variant="ghost" icon="lucide-x" :aria-label="'Remove ' + c.code" @click="delCode('tax', c.name)" />
          </div>
          <p v-if="!codes.tax_codes.some((x) => x.code_type === t)" class="sb-note py-1">No {{ t }} codes yet.</p>
        </div>
        <div class="mt-2 grid grid-cols-[90px_120px_1fr_auto] items-end gap-2">
          <FormControl type="select" v-model="newCode.code_type" :options="['SAC', 'HSN']" aria-label="Code type" />
          <FormControl v-model="newCode.code" placeholder="Code" aria-label="New code" />
          <FormControl v-model="newCode.description" placeholder="Description" aria-label="Description" />
          <Button label="+ Add" @click="() => { newCode.kind = 'tax'; addCode() }" />
        </div>
      </section>
      <section class="sb-card">
        <h2 class="text-base font-semibold">Purpose codes</h2><p class="sb-note mb-3">Starred codes show as one-click chips on the invoice.</p>
        <div v-for="c in codes.purpose_codes" :key="c.name" class="flex items-center gap-3 border-b border-outline-gray-1 py-1.5 text-p-sm">
          <button type="button" class="text-lg" :class="c.is_favourite ? 'text-ink-amber-5' : 'text-ink-gray-4'" :aria-label="(c.is_favourite ? 'Unstar ' : 'Star ') + c.code" @click="star('purpose', c.name)">{{ c.is_favourite ? '★' : '☆' }}</button>
          <b class="w-20">{{ c.code }}</b><span class="flex-1 text-ink-gray-6">{{ c.description }}</span>
          <Button variant="ghost" icon="lucide-x" :aria-label="'Remove ' + c.code" @click="delCode('purpose', c.name)" />
        </div>
        <div class="mt-2 grid grid-cols-[120px_1fr_auto] items-end gap-2">
          <FormControl v-model="newCode.code" placeholder="e.g. P1004" aria-label="New purpose code" />
          <FormControl v-model="newCode.description" placeholder="Description" aria-label="Purpose description" />
          <Button label="+ Add" @click="() => { newCode.kind = 'purpose'; addCode() }" />
        </div>
      </section>

      <section class="sb-card">
        <h2 class="text-base font-semibold">CBIC exchange rates</h2>
        <p class="sb-note mb-3">CBIC notifies rates on the 1st and 3rd Thursday of each month. SupaBill fetches them from AllRatesToday on those days and daily as a check. Each invoice uses the <b>export</b> rate in force on its date.</p>
        <div class="grid gap-2.5 sm:grid-cols-2">
          <FormControl type="select" label="Source" v-model="s.cbic_provider" :options="[{ label: 'AllRatesToday (automatic)', value: 'AllRatesToday' }, { label: 'Manual entry', value: 'Manual' }]" />
          <div>
            <FormControl type="password" label="AllRatesToday API key" v-model="secrets.allratestoday_api_key" autocomplete="new-password" :placeholder="s.has_allratestoday_api_key ? '•••••••• saved' : 'art_live_…'" />
            <div class="mt-1 flex items-center gap-2 text-xs text-ink-gray-5">{{ secretState('allratestoday_api_key') }}
              <button v-if="s.has_allratestoday_api_key && !clear.includes('allratestoday_api_key')" type="button" class="sb-link" @click="clear.push('allratestoday_api_key')">Remove</button></div>
          </div>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <Button :loading="busy.cbic" icon-left="lucide-refresh-cw" label="Fetch latest CBIC rates" @click="fetchCbic" />
          <span class="text-xs text-ink-gray-5">{{ s.cbic_last_status || 'Not fetched yet' }}</span>
        </div>
        <div class="mt-3 overflow-x-auto">
          <table class="sb-table">
            <thead><tr><th>Effective from</th><th>Currency</th><th class="sb-num">Export (₹)</th><th class="sb-num">Import (₹)</th><th>Source</th><th /></tr></thead>
            <tbody>
              <tr v-for="r in rates" :key="r.name">
                <td>{{ fmtDate(r.effective_from) }}</td><td>{{ r.currency }}</td><td class="sb-num font-semibold">{{ r.export_rate }}</td><td class="sb-num text-ink-gray-5">{{ +r.import_rate ? r.import_rate : '—' }}</td>
                <td><span class="sb-pill" :class="r.source === 'AllRatesToday' ? 'sb-ok' : r.source === 'Manual' ? 'sb-warn' : 'sb-mute'">{{ r.source }}</span></td>
                <td class="text-right"><Button variant="ghost" icon="lucide-x" :aria-label="'Remove rate ' + r.name" @click="delRate(r.name)" /></td>
              </tr>
              <tr v-if="!rates.length"><td colspan="6" class="py-4 text-center text-ink-gray-5">No rates yet</td></tr>
            </tbody>
          </table>
        </div>
        <div class="mt-2 grid grid-cols-2 items-end gap-2 sm:grid-cols-[150px_100px_1fr_1fr_auto]">
          <FormControl type="date" v-model="newRate.effective_from" aria-label="Effective from" />
          <FormControl type="select" v-model="newRate.currency" :options="CURR.filter((c) => c !== 'INR')" aria-label="Currency" />
          <FormControl type="number" v-model="newRate.export_rate" placeholder="Export rate" aria-label="Export rate" />
          <FormControl type="number" v-model="newRate.import_rate" placeholder="Import rate (optional)" aria-label="Import rate" />
          <Button label="+ Add" @click="addRate" />
        </div>
      </section>

      <section class="sb-card">
        <h2 class="text-base font-semibold">Excel sync (Microsoft 365)</h2>
        <p class="sb-note mb-3">New invoices are added to the workbook table; wallet ref, Received, bank charges and payment status are read back. Needs an Azure app registration — see the admin guide.</p>
        <div class="grid gap-2.5 sm:grid-cols-2">
          <FormControl class="sm:col-span-2" type="checkbox" label="Enable Excel sync" :model-value="!!s.excel_enabled" @update:model-value="(v: boolean) => (s.excel_enabled = v ? 1 : 0)" />
          <FormControl label="Tenant ID" v-model="s.ms_tenant_id" /><FormControl label="Client ID" v-model="s.ms_client_id" />
          <div class="sm:col-span-2">
            <FormControl type="password" label="Client secret" v-model="secrets.ms_client_secret" autocomplete="new-password" :placeholder="s.has_ms_client_secret ? '•••••••• saved' : ''" />
            <div class="mt-1 flex items-center gap-2 text-xs text-ink-gray-5">{{ secretState('ms_client_secret') }}
              <button v-if="s.has_ms_client_secret && !clear.includes('ms_client_secret')" type="button" class="sb-link" @click="clear.push('ms_client_secret')">Remove</button></div>
          </div>
          <FormControl class="sm:col-span-2" type="textarea" label="Workbook share link" v-model="s.workbook_share_link" />
          <FormControl label="Worksheet" v-model="s.worksheet_name" /><FormControl label="Excel table name" v-model="s.table_name" />
          <FormControl type="number" label="Read back every (minutes)" v-model="s.pull_interval_minutes" />
          <div class="sb-note self-end pb-1">Last push: {{ s.excel_last_push || '—' }}<br>Last read-back: {{ s.excel_last_pull || '—' }}</div>
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button :loading="busy.excelTest" label="Test connection" @click="excelTest" />
          <Button :loading="busy.excelSync" icon-left="lucide-refresh-cw" label="Sync now" @click="excelSync" />
          <span class="self-center text-xs text-ink-gray-5">Save settings first.</span>
        </div>
      </section>
      <div class="pb-8"><Button type="submit" variant="solid" :loading="saving" label="Save settings" /></div>
    </form>
  </PageFrame>
</template>
