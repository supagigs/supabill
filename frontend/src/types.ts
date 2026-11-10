export interface Client {
  name: string; client_name: string; contact_person?: string; email?: string; address?: string; country?: string
  project?: string; currency?: string; payment_terms_days?: number; tax_treatment?: string; wallet?: string
  payment_method?: string; purpose_code?: string; sac_code?: string; hsn_code?: string
  last_milestone?: string; last_billing_period?: string; last_amount?: number
}
export interface Wallet { name: string; is_upwork: number; settles_to?: string; complete: boolean; details: { label: string; value: string }[] }
export interface Code { code: string; code_type?: string; description: string; is_favourite: number }
export interface Boot {
  settings: Record<string, any>
  clients: Client[]
  wallets: Wallet[]
  tax_codes: Code[]
  purpose_codes: Code[]
  tax_treatments: string[]
  access: { has_access: boolean; is_manager: boolean }
}
export interface Item { description: string; sac_code: string; hsn_code: string; qty: number; rate: number }
export interface Preview {
  next_invoice: string; due_date: string; gst_return_period: string; subtotal: number; tax_total: number; grand_total: number
  items: { amount: number; tax_amount: number }[]; cbic_rate: number | null; cbic_rate_source: string
  cbic_rate_effective_from: string | null; amount_inr: number; readiness: { level: 'error' | 'warning'; message: string }[]
}
