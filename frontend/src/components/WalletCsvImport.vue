<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, Dialog, LoadingIndicator, toast } from 'frappe-ui'
import { call, uploadFile } from '@/api'

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ done: [] }>()

type Action = 'create' | 'update' | 'skip' | 'rename'
interface Row {
  row: number; wallet_name: string; original: string; is_upwork: number; details: { label: string; value: string }[]
  status: 'new' | 'exists' | 'error'; action: Action; errors: string[]; values: Record<string, string>
}
const step = ref<'upload' | 'review' | 'running' | 'done'>('upload')
const busy = ref(false)
const fileName = ref('')
const rows = ref<Row[]>([])
const existing = ref<Set<string>>(new Set())
const result = ref<any>(null)
const fileInput = ref<HTMLInputElement | null>(null)

watch(open, (v) => { if (v) reset() })
function reset() { step.value = 'upload'; rows.value = []; result.value = null; fileName.value = ''; busy.value = false }

async function pickFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!f) return
  if (!/\.csv$/i.test(f.name)) return toast.error('Choose a .csv file (save the template as CSV in Excel)')
  busy.value = true
  try {
    const url = await uploadFile(f)
    const r = await call('supabill.api.wallet_import.review_csv', { file_url: url })
    existing.value = new Set((r.existing_names as string[]).map((n) => n.toLowerCase()))
    rows.value = r.rows.map((x: any) => ({ ...x, original: x.wallet_name }))
    fileName.value = f.name
    if (!rows.value.length) return toast.error('The file has no wallet rows')
    step.value = 'review'
  } catch (err: any) { toast.error(err.message) } finally { busy.value = false }
}

/** Re-checks a row after the user renames it or changes the action. */
function problem(r: Row): string {
  if (r.action === 'skip') return ''
  const name = r.wallet_name.trim()
  if (!name) return 'Type a wallet name'
  const dup = rows.value.filter((o) => o !== r && o.action !== 'skip' && o.wallet_name.trim().toLowerCase() === name.toLowerCase()).length
  if (dup) return 'This name is used by another row'
  const exists = existing.value.has(name.toLowerCase())
  if (r.action === 'update' && !exists) return 'No wallet with this name to update'
  if (r.action !== 'update' && exists) return 'A wallet with this name exists — choose Update, Skip or another name'
  const other = r.errors.filter((e) => !/name/i.test(e))
  return other[0] || ''
}
function rename(r: Row, v: string) {
  r.wallet_name = v
  const exists = existing.value.has(v.trim().toLowerCase())
  // A name that is free means "import this row under that name"; a taken one keeps the user's choice.
  if (!exists) r.action = v.trim() === r.original ? 'create' : 'rename'
  else if (r.action !== 'update' && r.action !== 'skip') r.action = 'rename'
}
function choices(r: Row): { value: Action; label: string }[] {
  const exists = existing.value.has(r.wallet_name.trim().toLowerCase())
  return exists
    ? [{ value: 'update', label: 'Update existing' }, { value: 'skip', label: 'Skip' }, { value: 'rename', label: 'Import with a new name' }]
    : [{ value: r.wallet_name.trim() === r.original ? 'create' : 'rename', label: 'Create' }, { value: 'skip', label: 'Skip' }]
}
const blocking = computed(() => rows.value.filter((r) => problem(r)).length)
const summary = computed(() => {
  const c = { create: 0, update: 0, skip: 0 }
  for (const r of rows.value) c[r.action === 'rename' ? 'create' : r.action]++
  return c
})
const filled = (r: Row) => r.details.filter((d) => d.value).length

async function start() {
  busy.value = true
  try {
    const out = await call('supabill.api.wallet_import.run_csv', {
      rows: rows.value.map((r) => ({ row: r.row, action: r.action, wallet_name: r.wallet_name.trim(), values: r.values })),
    })
    if (!out.data_import) { result.value = { created: 0, updated: 0, skipped: out.skipped, failed: [], wallets: [] }; step.value = 'done'; return }
    step.value = 'running'
    for (let i = 0; i < 120; i++) {
      const st = await call('supabill.api.wallet_import.csv_status', { data_import: out.data_import }, { get: true })
      if (st.finished) { result.value = { ...st, skipped: st.skipped + out.skipped }; break }
      await new Promise((res) => setTimeout(res, 1500))
    }
    if (!result.value) throw new Error('The import is still running. Check back on the Wallets page in a minute.')
    step.value = 'done'
    emit('done')
  } catch (err: any) { toast.error(err.message); if (step.value === 'running') step.value = 'review' } finally { busy.value = false }
}
function downloadTemplate() { window.open('/api/method/supabill.api.wallet_import.download_template', '_blank') }
</script>

<template>
  <Dialog v-model:open="open" title="Import wallets from CSV" size="5xl">
    <div v-if="step === 'upload'" class="grid gap-4 text-p-sm">
      <ol class="list-decimal space-y-1 pl-5 text-ink-gray-7">
        <li>Download the template and fill in one row per wallet. Keep the header row.</li>
        <li><b>Wallet Name</b> is required. <b>Paid via Upwork</b>: Yes for wallets without bank details. Extra lines (Sort Code, BSB…) go in <b>Other Details</b> as “Label: value”, one per line.</li>
        <li>Upload it. You will see every row and choose what happens to names that already exist before anything is saved.</li>
      </ol>
      <div class="flex flex-wrap gap-2">
        <Button icon-left="lucide-download" label="Download CSV template" @click="downloadTemplate" />
        <Button variant="solid" icon-left="lucide-upload" :loading="busy" label="Upload filled CSV" @click="fileInput?.click()" />
        <input ref="fileInput" type="file" accept=".csv,text/csv" class="hidden" aria-label="CSV file" @change="pickFile" />
      </div>
      <p class="sb-note">The import runs through Frappe's Data Import, so each run is also logged under Data Import in the desk.</p>
    </div>

    <div v-else-if="step === 'review'" class="grid gap-3 text-p-sm">
      <div class="flex flex-wrap items-center gap-2">
        <b>{{ fileName }}</b> · {{ rows.length }} row{{ rows.length === 1 ? '' : 's' }}
        <span class="sb-pill sb-ok">{{ summary.create }} create</span>
        <span class="sb-pill sb-warn">{{ summary.update }} update</span>
        <span class="sb-pill sb-mute">{{ summary.skip }} skip</span>
        <span v-if="blocking" class="sb-pill sb-bad">{{ blocking }} to fix</span>
      </div>
      <div class="max-h-[55vh] overflow-auto rounded-4 border border-outline-gray-2">
        <table class="sb-table">
          <thead class="sticky top-0 bg-surface-base"><tr><th class="pl-3">Row</th><th>Wallet name</th><th>In SupaBill</th><th>What to do</th><th>Bank lines</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.row" :class="{ 'opacity-60': r.action === 'skip' }">
              <td class="pl-3 text-ink-gray-5">{{ r.row }}</td>
              <td><input class="cell w-52" :value="r.wallet_name" :aria-label="`Wallet name, row ${r.row}`" @input="(e: any) => rename(r, e.target.value)" /></td>
              <td><span class="sb-pill" :class="existing.has(r.wallet_name.trim().toLowerCase()) ? 'sb-warn' : 'sb-ok'">{{ existing.has(r.wallet_name.trim().toLowerCase()) ? 'Exists' : 'New' }}</span></td>
              <td>
                <select class="cell" :value="r.action" :aria-label="`Action, row ${r.row}`" @change="(e: any) => (r.action = e.target.value)">
                  <option v-for="c in choices(r)" :key="c.value" :value="c.value">{{ c.label }}</option>
                </select>
              </td>
              <td class="text-xs text-ink-gray-6" :title="r.details.map((d) => d.label + ': ' + (d.value || '—')).join('\n')">
                {{ r.is_upwork && !r.details.length ? 'Paid via Upwork' : `${filled(r)} of ${r.details.length} filled` }}
              </td>
              <td class="text-xs" :class="problem(r) ? 'text-ink-red-5' : 'text-ink-gray-5'">
                {{ problem(r) || (r.action === 'update' ? 'Filled cells replace the current values; blank cells keep them' : '') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex justify-end gap-2">
        <Button label="Choose another file" @click="reset" />
        <Button variant="solid" :loading="busy" :disabled="!!blocking" :label="`Import ${summary.create + summary.update} wallet${summary.create + summary.update === 1 ? '' : 's'}`" @click="start" />
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
      <ul v-if="result.wallets.length" class="list-disc pl-5"><li v-for="w in result.wallets" :key="w.wallet_name">{{ w.wallet_name }} — {{ w.result }}</li></ul>
      <ul v-if="result.failed.length" class="list-disc pl-5 text-ink-red-6"><li v-for="(f, i) in result.failed" :key="i">Row {{ f.rows.join(', ') }}: {{ f.message }}</li></ul>
      <div class="flex justify-end gap-2"><Button label="Import another file" @click="reset" /><Button variant="solid" label="Done" @click="open = false" /></div>
    </div>
  </Dialog>
</template>

<style scoped>
.cell { @apply h-7 py-0 leading-7 rounded-3 border border-outline-gray-2 bg-transparent px-1.5 text-p-sm text-ink-gray-8 focus:border-outline-gray-4 focus:outline-none; }
</style>
