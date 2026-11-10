<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Button, Dialog, Dropdown, FormControl, LoadingIndicator, toast, dialog } from 'frappe-ui'
import WalletCsvImport from '@/components/WalletCsvImport.vue'
import PageFrame from '@/components/PageFrame.vue'
import { call, uploadFile } from '@/api'

const list = ref<any[] | null>(null)
const sel = ref<string | null>(null)
const ad = ref('')
const saving = ref(false)
const form = reactive<{ wallet_name: string; is_upwork: number; settles_to: string; disabled: number; details: { label: string; value: string }[] }>({
  wallet_name: '', is_upwork: 0, settles_to: 'IDFC FIRST Bank', disabled: 0, details: [],
})
const csvOpen = ref(false)
const pdfInput = ref<HTMLInputElement | null>(null)
const pdfBusy = ref(false)
const fromPdf = ref('')
const clash = ref<{ open: boolean; name: string }>({ open: false, name: '' })
const nameInput = ref<any>(null)
const TEMPLATE = ['Beneficiary Name', 'Account Number', 'Routing / SWIFT Code', 'Account Type', 'Bank Name', 'Bank Address', 'Bank Country']

async function load() {
  list.value = await call('supabill.api.setup.list_wallets', {}, { get: true })
}
function pick(name: string | null) {
  sel.value = name
  const w = name ? list.value?.find((x) => x.name === name) : null
  Object.assign(form, w
    ? { wallet_name: w.wallet_name, is_upwork: w.is_upwork, settles_to: w.settles_to || '', disabled: w.disabled, details: w.details.map((d: any) => ({ ...d })) }
    : { wallet_name: '', is_upwork: 0, settles_to: 'IDFC FIRST Bank', disabled: 0, details: TEMPLATE.map((label) => ({ label, value: '' })) })
}
async function save() {
  // A new wallet whose name already exists: let the user update that wallet, rename, or cancel.
  if (!sel.value) {
    const hit = list.value?.find((w) => w.name.toLowerCase() === form.wallet_name.trim().toLowerCase())
    if (hit) { clash.value = { open: true, name: hit.name }; return }
  }
  saving.value = true
  try {
    const doc = await call('supabill.api.setup.save_wallet', { values: form, name: sel.value })
    toast.success('Wallet saved')
    await load()
    pick(doc.name)
    fromPdf.value = ''
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
function remove() {
  const name = sel.value!
  dialog.confirm({
    title: `Delete ${name}?`, message: 'Wallets used by invoices or clients can only be disabled.', confirmLabel: 'Delete', theme: 'red',
    onConfirm: async () => {
      try { await call('supabill.api.setup.delete_wallet', { name }); toast.success('Deleted'); await load(); pick(list.value?.[0]?.name ?? null) } catch (e: any) { toast.error(e.message) }
    },
  } as any)
}
async function importPdf(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  if (!/\.pdf$/i.test(f.name)) return toast.error('Choose a PDF file')
  pdfBusy.value = true
  try {
    let url: string
    try { url = await uploadFile(f) } catch { throw new Error('This PDF could not be uploaded. It may be damaged or password-protected.') }
    const out = await call('supabill.api.wallet_import.read_pdf', { file_url: url })
    pick(null)
    form.details = out.details.map((d: any) => ({ label: d.label, value: d.value }))
    fromPdf.value = f.name
    toast.success(`${out.details.length} bank line${out.details.length === 1 ? '' : 's'} read from the PDF`)
  } catch (err: any) { toast.error(err.message) } finally { pdfBusy.value = false }
}
/** Update chosen: the existing wallet's lines, with the imported values filled in on top. */
function useExisting() {
  const w = list.value!.find((x) => x.name === clash.value.name)!
  const merged = w.details.map((d: any) => ({ ...d }))
  for (const d of form.details) {
    const hit = merged.find((m: any) => m.label.trim().toLowerCase() === d.label.trim().toLowerCase())
    if (hit) { if (d.value.trim()) hit.value = d.value.trim() } else if (d.value.trim()) merged.push({ label: d.label, value: d.value.trim() })
  }
  const keepPdf = fromPdf.value
  pick(w.name)
  form.details = merged
  fromPdf.value = keepPdf
  clash.value.open = false
  toast.success(`Merged into ${w.name}. Review the lines and press Save.`)
}
function renameNew() {
  clash.value.open = false
  setTimeout(() => (document.querySelector('#wallet-name-input input') as HTMLInputElement | null)?.select(), 50)
}
const importOptions = [
  { label: 'From invoice PDF (one wallet)', icon: 'lucide-file-text', onClick: () => pdfInput.value?.click() },
  { label: 'From CSV (many wallets)', icon: 'lucide-sheet', onClick: () => (csvOpen.value = true) },
]
const complete = (w: any) => w.is_upwork || (w.details.length && w.details.every((d: any) => (d.value || '').trim()))
onMounted(async () => {
  await load()
  try { ad.value = (await call('supabill.api.setup.get_settings', {}, { get: true })).ad_bank_name || '' } catch { /* manager only */ }
  pick(list.value?.[0]?.name ?? null)
})
</script>

<template>
  <PageFrame title="Wallets & banks" subtitle="Collection accounts printed on invoices">
    <template #actions>
      <Dropdown :options="importOptions" align="end" :button="{ label: 'Import wallet', iconLeft: 'lucide-upload', loading: pdfBusy }" />
      <Button variant="solid" icon-left="lucide-plus" label="New wallet" @click="pick(null); fromPdf = ''" />
      <input ref="pdfInput" type="file" accept=".pdf,application/pdf" class="hidden" aria-label="Invoice PDF" @change="importPdf" />
    </template>
    <div v-if="!list" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <template v-else>
      <div class="sb-card mb-4 flex items-center gap-3">
        <span class="lucide-landmark size-5 text-ink-gray-5" aria-hidden="true" />
        <div class="text-p-sm"><b>All wallets settle into {{ ad || 'your AD bank' }}.</b> <span class="text-ink-gray-5">Edit it in Settings → AD bank. Each wallet below holds the collection account printed under “Bank transfer details”.</span></div>
      </div>
      <div class="grid gap-4 md:grid-cols-[240px_1fr]">
        <nav class="sb-card !p-2" aria-label="Wallets">
          <button v-for="w in list" :key="w.name" type="button" class="flex w-full items-center justify-between gap-2 rounded-4 px-3 py-2 text-left text-p-sm hover:bg-surface-gray-2" :class="{ 'bg-surface-gray-3 font-semibold': w.name === sel }" @click="pick(w.name)">
            <span>{{ w.name }} <span v-if="w.disabled" class="text-xs text-ink-gray-4">(off)</span></span>
            <span class="text-xs font-normal" :class="complete(w) ? 'text-ink-green-5' : 'text-ink-amber-5'">{{ complete(w) ? '✓ complete' : 'details missing' }}</span>
          </button>
          <p v-if="!list.length" class="p-3 text-p-sm text-ink-gray-5">No wallets yet.</p>
        </nav>
        <section class="sb-card">
          <div class="sb-sect">{{ sel ? sel + ' — collection account' : 'New wallet' }}</div>
          <form class="grid grid-cols-2 gap-2.5" @submit.prevent="save">
            <div v-if="fromPdf" class="col-span-2 rounded-4 border border-outline-blue-2 bg-surface-blue-1 p-3 text-p-sm">
              <b>Filled from {{ fromPdf }}.</b> Check every line against the PDF{{ sel ? '' : ', type a wallet name' }}, then Save. Nothing is saved until you do.
            </div>
            <div id="wallet-name-input"><FormControl label="Wallet name" v-model="form.wallet_name" required /></div>
            <FormControl label="Settles to" v-model="form.settles_to" />
            <FormControl type="checkbox" label="Paid via Upwork (no bank details needed)" :model-value="!!form.is_upwork" @update:model-value="(v: boolean) => (form.is_upwork = v ? 1 : 0)" />
            <FormControl type="checkbox" label="Disabled" :model-value="!!form.disabled" @update:model-value="(v: boolean) => (form.disabled = v ? 1 : 0)" />
            <div class="col-span-2 mt-2 sb-lbl">Bank transfer details</div>
            <div v-for="(d, i) in form.details" :key="i" class="col-span-2 grid grid-cols-[minmax(120px,200px)_1fr_auto] items-end gap-2">
              <FormControl v-model="d.label" :aria-label="`Label ${i + 1}`" />
              <FormControl v-model="d.value" :placeholder="'Enter ' + (d.label || 'value').toLowerCase()" :aria-label="d.label || `Value ${i + 1}`" />
              <Button variant="ghost" icon="lucide-x" :aria-label="`Remove ${d.label}`" @click="form.details.splice(i, 1)" />
            </div>
            <div class="col-span-2 mt-2 flex flex-wrap gap-2">
              <Button type="submit" variant="solid" :loading="saving" label="Save" />
              <Button label="+ Field (SWIFT, IBAN, IFSC…)" @click="form.details.push({ label: '', value: '' })" />
              <Button v-if="sel" theme="red" label="Delete" @click="remove" />
            </div>
          </form>
        </section>
      </div>
    </template>
    <WalletCsvImport v-model:open="csvOpen" @done="load" />
    <Dialog v-model:open="clash.open" :title="`${clash.name} already exists`">
      <p class="mb-4 text-p-sm text-ink-gray-7">Update that wallet with these details (filled lines replace its values, the rest stay), or give this wallet another name.</p>
      <div class="flex flex-wrap justify-end gap-2">
        <Button label="Cancel" @click="clash.open = false" />
        <Button label="Use another name" @click="renameNew" />
        <Button variant="solid" :label="`Update ${clash.name}`" @click="useExisting" />
      </div>
    </Dialog>
  </PageFrame>
</template>
