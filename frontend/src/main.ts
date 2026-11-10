import { createApp } from 'vue'
import { setConfig, frappeRequest, useColorScheme } from 'frappe-ui'
import App from './App.vue'
import { router } from './router'
import './index.css'

setConfig('resourceFetcher', frappeRequest)
useColorScheme() // restores the saved light/dark choice before first paint

createApp(App).use(router).mount('#app')
