<script setup lang="ts">
import { computed } from 'vue'
import { money, fmtDate } from '@/format'

const props = defineProps<{
  s: Record<string, any>
  f: Record<string, any>
  items: { description: string; sac_code: string; hsn_code: string; qty: number; rate: number }[]
  lineDesc: (i: number) => string
  totals: { subtotal: number; tax_total: number; grand_total: number; items: { amount: number; tax_amount: number }[] } | null
  invoiceNo: string
  dueDate: string
  bank: { label: string; value: string }[]
}>()
const cur = computed(() => props.f.currency)
const lut = computed(() => props.f.tax_treatment === 'Export under LUT')
const hasHsn = computed(() => props.items.some((i) => i.hsn_code))
const lines = (t?: string) => (t || '').split('\n').filter(Boolean)
</script>

<template>
  <article class="paper mx-auto max-w-[820px] rounded-3 bg-white px-6 py-8 text-[12.5px] leading-relaxed text-[#1b1f2a] shadow-2xl sm:px-11 sm:py-10">
    <header class="mb-5 flex items-end justify-between gap-3 border-b-[3px] border-[#16213e] pb-3">
      <div class="text-lg font-bold text-[#16213e]">{{ s.legal_name }}</div>
      <div class="text-2xl font-bold tracking-[.12em] text-[#16213e]">{{ lut ? 'INVOICE' : 'TAX INVOICE' }}</div>
    </header>
    <section class="mb-5 grid gap-6 sm:grid-cols-2">
      <div>
        <div class="lb">FROM</div>
        <b>{{ s.display_name || s.legal_name }}</b>
        <div v-for="l in lines(s.company_address)" :key="l">{{ l }}</div>
        <div class="mt-3">Email: {{ s.company_email }}</div>
        <div>Contact: {{ s.company_phone }}</div>
        <div>GSTIN: {{ s.gstin }}</div><div>PAN: {{ s.pan }}</div><div>IEC: {{ s.iec }}</div>
      </div>
      <div>
        <div class="lb">INVOICE DETAILS</div>
        <dl class="grid grid-cols-[120px_1fr] gap-y-0.5">
          <dt class="text-[#5b6475]">Invoice No:</dt><dd class="font-semibold">{{ invoiceNo }}</dd>
          <dt class="text-[#5b6475]">Invoice Date:</dt><dd>{{ fmtDate(f.invoice_date) }}</dd>
          <dt class="text-[#5b6475]">Due Date:</dt><dd>{{ fmtDate(dueDate) }}</dd>
          <dt class="text-[#5b6475]">Country of Supply:</dt><dd>{{ f.country_of_supply }}</dd>
          <template v-if="f.purpose_code"><dt class="text-[#5b6475]">Purpose Code:</dt><dd>{{ f.purpose_code }}</dd></template>
          <dt class="text-[#5b6475]">Currency:</dt><dd>{{ cur }}</dd>
        </dl>
      </div>
    </section>
    <section class="mb-5 grid gap-6 sm:grid-cols-2">
      <div>
        <div class="lb">BILL TO</div>
        <b>{{ f.client_name }}</b>
        <div v-for="l in lines(f.billing_address)" :key="l">{{ l }}</div>
        <div v-if="!f.billing_address" class="font-semibold text-[#c27400]">address missing</div>
        <div class="mt-3" v-if="f.attention">Attn: {{ f.attention }}</div>
        <div v-if="f.client_email">Email: {{ f.client_email }}</div>
      </div>
      <div>
        <div class="lb">PROJECT &amp; PAYMENT</div>
        <b>{{ f.project }}</b>
        <div>{{ f.milestone }}<template v-if="f.billing_period"> – Billing period: {{ f.billing_period }}</template></div>
        <div class="mt-3">Payment Terms: {{ +f.payment_terms_days ? 'Payable by ' + fmtDate(dueDate) : 'Due on receipt' }}</div>
        <div>Payment Method: {{ f.payment_method }}</div>
      </div>
    </section>
    <div class="overflow-x-auto">
      <table class="mb-4 w-full border-collapse">
        <thead>
          <tr class="bg-[#16213e] text-left text-[11px] text-white">
            <th class="p-2">#</th><th class="p-2">Item Description</th><th v-if="hasHsn" class="p-2">HSN</th><th class="p-2">SAC Code</th>
            <th class="p-2 text-right">Unit Price</th><th class="p-2 text-right">Qty</th><th class="p-2 text-right">Tax</th><th class="p-2 text-right">Line Total</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(it, i) in items" :key="i" class="border-b border-[#e6e9ef] align-top">
            <td class="p-2">{{ i + 1 }}</td><td class="p-2">{{ lineDesc(i) }}</td><td v-if="hasHsn" class="p-2">{{ it.hsn_code }}</td><td class="p-2">{{ it.sac_code }}</td>
            <td class="p-2 text-right">{{ money(it.rate, cur) }}</td><td class="p-2 text-right">{{ it.qty }}</td>
            <td class="p-2 text-right">{{ money(totals?.items[i]?.tax_amount, cur) }}</td>
            <td class="p-2 text-right">{{ money(totals?.items[i]?.amount, cur) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="ml-auto w-full max-w-[310px]">
      <div class="flex justify-between border-b border-[#eef0f4] py-1"><span>Sub Total</span><span>{{ money(totals?.subtotal, cur) }}</span></div>
      <template v-if="f.tax_treatment === 'CGST + SGST 9%'">
        <div class="flex justify-between border-b border-[#eef0f4] py-1"><span>CGST 9%</span><span>{{ money((totals?.tax_total || 0) / 2, cur) }}</span></div>
        <div class="flex justify-between border-b border-[#eef0f4] py-1"><span>SGST 9%</span><span>{{ money((totals?.tax_total || 0) / 2, cur) }}</span></div>
      </template>
      <div v-else class="flex justify-between border-b border-[#eef0f4] py-1"><span>{{ f.tax_treatment === 'IGST 18%' ? 'IGST 18%' : 'Tax Payable' }}</span><span>{{ money(totals?.tax_total, cur) }}</span></div>
      <div class="flex justify-between border-t-2 border-[#16213e] pt-2 text-sm font-bold"><span>Total Due ({{ cur }})</span><span>{{ money(totals?.grand_total, cur) }}</span></div>
    </div>
    <section class="mt-6 grid gap-6 text-[11.5px] sm:grid-cols-2">
      <div><div class="lb">NOTES</div><b v-if="lut">LUT</b><div class="whitespace-pre-line">{{ f.notes }}</div></div>
      <div>
        <div class="lb">BANK TRANSFER DETAILS</div>
        <div v-for="b in bank" :key="b.label">{{ b.label }}: <span v-if="b.value">{{ b.value }}</span><span v-else class="font-semibold text-[#c27400]">— missing —</span></div>
      </div>
    </section>
  </article>
</template>

<style scoped>
.lb { font-size: 10.5px; font-weight: 700; letter-spacing: .1em; color: #5b6475; border-bottom: 1px solid #dfe3ea; padding-bottom: 4px; margin-bottom: 8px; }
</style>
