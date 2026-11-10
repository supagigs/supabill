export interface NavItem {
  name: string
  label: string
  icon: string
  managerOnly?: boolean
}
export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    label: 'Billing',
    items: [
      { name: 'NewInvoice', label: 'New invoice', icon: 'lucide-plus' },
      { name: 'Register', label: 'Sales register', icon: 'lucide-table-2' },
    ],
  },
  {
    label: 'Compliance',
    items: [
      { name: 'Edf', label: 'EDF filing', icon: 'lucide-file-check' },
      { name: 'Realisation', label: 'Realisation tracker', icon: 'lucide-clock' },
    ],
  },
  {
    label: 'Setup',
    items: [
      { name: 'Clients', label: 'Clients', icon: 'lucide-users' },
      { name: 'Wallets', label: 'Wallets & banks', icon: 'lucide-wallet', managerOnly: true },
      { name: 'Settings', label: 'Settings', icon: 'lucide-settings', managerOnly: true },
    ],
  },
]
