<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Button, FormControl, LoadingIndicator, toast, dialog } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'

const list = ref<any[] | null>(null)
const sel = ref<string | null>(null)
const ad = ref('')
const saving = ref(false)
const form = reactive<{ wallet_name: string; is_upwork: number; settles_to: string; disabled: number; details: { label: string; value: string }[] }>({
  wallet_name: '', is_upwork: 0, settles_to: 'IDFC FIRST Bank', disabled: 0, details: [],
})
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
  saving.value = true
  try {
    const doc = await call('supabill.api.setup.save_wallet', { values: form, name: sel.value })
    toast.success('Wallet saved')
    await load()
    pick(doc.name)
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
const complete = (w: any) => w.is_upwork || (w.details.length && w.details.every((d: any) => (d.value || '').trim()))
onMounted(async () => {
  await load()
  try { ad.value = (await call('supabill.api.setup.get_settings', {}, { get: true })).ad_bank_name || '' } catch { /* manager only */ }
  pick(list.value?.[0]?.name ?? null)
})
</script>

<template>
  <PageFrame title="Wallets & banks" subtitle="Collection accounts printed on invoices">
    <template #actions><Button variant="solid" icon-left="lucide-plus" label="New wallet" @click="pick(null)" /></template>
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
            <FormControl label="Wallet name" v-model="form.wallet_name" required />
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
  </PageFrame>
</template>
