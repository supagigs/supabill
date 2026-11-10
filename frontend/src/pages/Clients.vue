<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, FormControl, LoadingIndicator, toast, dialog } from 'frappe-ui'
import PageFrame from '@/components/PageFrame.vue'
import { call } from '@/api'
import { inr } from '@/format'
import { session } from '@/session'

const route = useRoute()
const router = useRouter()
const rows = ref<any[] | null>(null)
const wallets = ref<string[]>([])
const purposes = ref<{ code: string; description: string }[]>([])
const search = ref('')
const editing = ref<string | null>(null) // null = new
const saving = ref(false)
const form = reactive<Record<string, any>>({})
const TAX = ['Export under LUT', 'IGST 18%', 'CGST + SGST 9%']
const METHODS = ['ACH bank transfer', 'Wire transfer (SWIFT)', 'Upwork', 'NEFT / RTGS / UPI']
const TERMS = [0, 7, 15, 21, 30, 45].map((d) => ({ label: d ? `Net ${d}` : 'Due on receipt', value: d }))

const blank = () => ({
  client_name: '', contact_person: '', email: '', address: '', country: '', project: '', currency: 'USD',
  payment_terms_days: 21, tax_treatment: 'Export under LUT', wallet: '', payment_method: 'ACH bank transfer',
  purpose_code: '', sac_code: '', hsn_code: '', last_milestone: '', last_billing_period: '', last_amount: 0, disabled: 0,
})
const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return (rows.value || []).filter((r) => !q || [r.client_name, r.contact_person, r.project].join(' ').toLowerCase().includes(q))
})

async function load() {
  const [c, w, codes] = await Promise.all([
    call('supabill.api.setup.list_clients', {}, { get: true }),
    call('supabill.api.setup.list_wallets', {}, { get: true }),
    call('supabill.api.setup.list_codes', {}, { get: true }),
  ])
  rows.value = c
  wallets.value = w.filter((x: any) => !x.disabled).map((x: any) => x.name)
  purposes.value = codes.purpose_codes
}
function edit(name: string | null) {
  editing.value = name
  Object.assign(form, blank(), name ? rows.value?.find((r) => r.name === name) : {})
  if (!name) form.wallet = wallets.value[0] || ''
}
async function save() {
  saving.value = true
  try {
    const doc = await call('supabill.api.setup.save_client', { values: form, name: editing.value })
    toast.success(editing.value ? 'Client saved' : `${doc.client_name} added`)
    await load()
    editing.value = doc.name
  } catch (e: any) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}
function remove() {
  const name = editing.value!
  dialog.confirm({
    title: `Delete ${name}?`,
    message: 'Clients with invoices cannot be deleted; disable them instead.',
    confirmLabel: 'Delete',
    theme: 'red',
    onConfirm: async () => {
      try {
        await call('supabill.api.setup.delete_client', { name })
        toast.success(`${name} deleted`)
        await load()
        edit(rows.value?.[0]?.name ?? null)
      } catch (e: any) {
        toast.error(e.message)
      }
    },
  } as any)
}
onMounted(async () => {
  await load()
  if (route.query.new) edit(null)
  else edit(rows.value?.[0]?.name ?? null)
})
watch(() => route.query.new, (v) => v && edit(null))
</script>

<template>
  <PageFrame title="Clients" subtitle="Saved clients fill in every invoice">
    <template #actions><Button variant="solid" icon-left="lucide-plus" label="New client" @click="edit(null)" /></template>
    <div v-if="!rows" class="flex justify-center py-20"><LoadingIndicator class="size-6" /></div>
    <div v-else class="grid gap-4 xl:grid-cols-[1fr_420px]">
      <section class="sb-card min-w-0">
        <FormControl v-model="search" placeholder="Search clients…" class="mb-3" aria-label="Search clients" />
        <div class="overflow-x-auto">
          <table class="sb-table">
            <thead><tr><th>Client</th><th>Project</th><th>Wallet</th><th>Terms</th><th class="sb-num">Invoices</th><th class="sb-num">Billed (₹)</th></tr></thead>
            <tbody>
              <tr v-for="r in filtered" :key="r.name" class="click" :class="{ on: r.name === editing }" @click="edit(r.name)">
                <td><div class="font-medium">{{ r.client_name }} <span v-if="r.disabled" class="sb-pill sb-mute ml-1">disabled</span></div><div class="text-xs text-ink-gray-5">{{ [r.contact_person, r.country].filter(Boolean).join(' · ') || '—' }}</div></td>
                <td>{{ r.project || '—' }}</td><td>{{ r.wallet || '—' }}</td>
                <td>{{ +r.payment_terms_days ? 'Net ' + r.payment_terms_days : 'On receipt' }}</td>
                <td class="sb-num">{{ r.invoice_count }}</td><td class="sb-num">{{ r.invoice_count ? inr(r.billed_inr) : '—' }}</td>
              </tr>
              <tr v-if="!filtered.length"><td colspan="6" class="py-8 text-center text-ink-gray-5">{{ rows.length ? 'No clients match' : 'No clients yet — add your first one' }}</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section class="sb-card">
        <div class="sb-sect">{{ editing ? 'Edit client' : 'New client' }}</div>
        <form class="grid grid-cols-2 gap-2.5" @submit.prevent="save">
          <FormControl class="col-span-2" label="Client / company name" v-model="form.client_name" required />
          <FormControl label="Contact person" v-model="form.contact_person" />
          <FormControl label="Contact email" type="email" v-model="form.email" />
          <FormControl class="col-span-2" type="textarea" label="Billing address" v-model="form.address" />
          <FormControl label="Country (for EDF)" v-model="form.country" />
          <FormControl label="Default project" v-model="form.project" />
          <FormControl type="select" label="Currency" v-model="form.currency" :options="['USD', 'INR', 'EUR', 'GBP', 'AUD', 'CAD']" />
          <FormControl type="select" label="Payment terms" v-model="form.payment_terms_days" :options="TERMS" />
          <FormControl type="select" label="Receive via (wallet)" v-model="form.wallet" :options="wallets" />
          <FormControl type="select" label="Payment method" v-model="form.payment_method" :options="METHODS" />
          <FormControl type="select" label="Tax treatment" v-model="form.tax_treatment" :options="TAX" />
          <FormControl type="select" label="Purpose code" v-model="form.purpose_code" :options="[{ label: '—', value: '' }, ...purposes.map((p) => ({ label: p.code + ' · ' + p.description, value: p.code }))]" />
          <FormControl label="SAC code" v-model="form.sac_code" />
          <FormControl label="HSN code" v-model="form.hsn_code" />
          <FormControl label="Last milestone" v-model="form.last_milestone" />
          <FormControl type="number" label="Last amount" v-model="form.last_amount" />
          <FormControl class="col-span-2" type="checkbox" label="Disabled (hidden from new invoices)" :model-value="!!form.disabled" @update:model-value="(v: boolean) => (form.disabled = v ? 1 : 0)" />
          <div class="col-span-2 mt-2 flex flex-wrap gap-2">
            <Button type="submit" variant="solid" :loading="saving" :label="editing ? 'Save' : 'Add client'" />
            <Button v-if="editing" label="New invoice →" @click="router.push({ name: 'NewInvoice', query: { client: editing } })" />
            <Button v-if="editing && session.isManager" theme="red" label="Delete" @click="remove" />
          </div>
        </form>
      </section>
    </div>
  </PageFrame>
</template>
