import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { session } from './session'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'NewInvoice' } },
  { path: '/new', name: 'NewInvoice', component: () => import('./pages/NewInvoice.vue'), meta: { title: 'New invoice' } },
  { path: '/register', name: 'Register', component: () => import('./pages/Register.vue'), meta: { title: 'Sales register' } },
  { path: '/edf', name: 'Edf', component: () => import('./pages/Edf.vue'), meta: { title: 'EDF filing' } },
  { path: '/realisation', name: 'Realisation', component: () => import('./pages/Realisation.vue'), meta: { title: 'Realisation tracker' } },
  { path: '/clients', name: 'Clients', component: () => import('./pages/Clients.vue'), meta: { title: 'Clients' } },
  { path: '/wallets', name: 'Wallets', component: () => import('./pages/Wallets.vue'), meta: { title: 'Wallets & banks', managerOnly: true } },
  { path: '/settings', name: 'Settings', component: () => import('./pages/Settings.vue'), meta: { title: 'Settings', managerOnly: true } },
  { path: '/no-access', name: 'NoAccess', component: () => import('./pages/NoAccess.vue'), meta: { title: 'No access', public: true } },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('./pages/NotFound.vue'), meta: { title: 'Not found', public: true } },
]

export const router = createRouter({ history: createWebHistory('/supabill/'), routes })

router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!session.hasAccess) return { name: 'NoAccess' }
  if (to.meta.managerOnly && !session.isManager) return { name: 'NoAccess', query: { need: 'manager' } }
  return true
})

router.afterEach((to) => {
  document.title = `${(to.meta.title as string) || 'SupaBill'} · SupaBill`
})
