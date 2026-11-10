import { onBeforeUnmount, ref } from 'vue'

/** True below Tailwind's `md` breakpoint; drives the Desktop/Mobile shell swap. */
export function useIsMobile() {
  const q = window.matchMedia('(max-width: 767px)')
  const isMobile = ref(q.matches)
  const on = (e: MediaQueryListEvent) => (isMobile.value = e.matches)
  q.addEventListener('change', on)
  onBeforeUnmount(() => q.removeEventListener('change', on))
  return isMobile
}
