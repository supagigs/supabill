/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
interface Window {
  csrf_token?: string
  site_name?: string
  sb_user?: string
  sb_full_name?: string
  sb_has_access?: boolean
  sb_is_manager?: boolean
}
