export const SYM: Record<string, string> = { USD: '$', INR: '₹', EUR: '€', GBP: '£', AUD: 'A$', CAD: 'C$' }

export function money(n: number | null | undefined, cur?: string): string {
  return (SYM[cur || ''] ?? (cur ? cur + ' ' : '')) + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
export function inr(n: number | null | undefined): string {
  return '₹' + Math.round(Number(n || 0)).toLocaleString('en-IN')
}
export function inrDec(n: number | null | undefined): string {
  return n === null || n === undefined || (n as any) === '' ? '' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })
}
export function fmtDate(s?: string | null): string {
  if (!s) return ''
  return new Date(s + 'T00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
export function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function monthLabel(k: string): string {
  return new Date(k + '-01T00:00').toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
}
