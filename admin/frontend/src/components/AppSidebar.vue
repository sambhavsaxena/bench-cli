<script setup>
import { Sidebar, SidebarItem, Dialog } from 'frappe-ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import LucideActivity from '~icons/lucide/activity'
import LucideCamera from '~icons/lucide/camera'
import LucideDatabase from '~icons/lucide/database'
import LucideFileText from '~icons/lucide/file-text'
import LucideGlobe from '~icons/lucide/globe'
import LucideListTodo from '~icons/lucide/list-todo'
import LucideLogOut from '~icons/lucide/log-out'
import LucidePackage2 from '~icons/lucide/package-2'
import LucideStore from '~icons/lucide/store'
import LucideSettings from '~icons/lucide/settings'
import LucideRepeat from '~icons/lucide/repeat'
import LucideCheck from '~icons/lucide/check'

const emit = defineEmits(['logout', 'open-settings'])

const route = useRoute()

const benches = ref([])
const showBenchDialog = ref(false)
const currentPort = window.location.port

async function loadBenches() {
  try {
    const response = await fetch('/api/benches/')
    if (response.ok) {
      benches.value = await response.json()
    }
  } catch { }
}

function openBenchDialog() {
  loadBenches()
  showBenchDialog.value = true
}

function switchBench(port) {
  if (String(port) === String(currentPort)) return
  window.location.href = `${window.location.protocol}//${window.location.hostname}:${port}`
}

const header = {
  title: 'Bench',
  logo: '/logos/frappe-icon.png',
  menuItems: [
    { label: 'Settings', icon: LucideSettings, onClick: () => emit('open-settings') },
    { label: 'Change Bench', icon: LucideRepeat, onClick: openBenchDialog },
    { label: 'Logout', icon: LucideLogOut, onClick: () => logout() },
  ],
}

const baseNavItems = [
  { label: 'Sites', to: '/', icon: LucideGlobe },
  { label: 'Apps', to: '/apps', icon: LucidePackage2 },
  { label: 'Marketplace', to: '/marketplace', icon: LucideStore },
  { label: 'Monitor', to: '/monitor', icon: LucideActivity },
  { label: 'Logs', to: '/logs', icon: LucideFileText },
  { label: 'Database', to: '/database', icon: LucideDatabase },
  { label: 'Tasks', to: '/tasks', icon: LucideListTodo },
]

const snapshotsEnabled = ref(false)
const runningCount = ref(0)
let pollTimer = null

const navItems = computed(() => [
  ...baseNavItems,
  ...(snapshotsEnabled.value ? [{ label: 'Snapshots', to: '/snapshots', icon: LucideCamera }] : []),
])

const sections = computed(() => [{ items: navItems.value }])

function isActive(to) {
  if (to === '/') return route.path === '/' || route.path.startsWith('/sites')
  return route.path.startsWith(to)
}

async function pollRunning() {
  try {
    const response = await fetch('/api/tasks/?status=running')
    if (response.ok) {
      const tasks = await response.json()
      runningCount.value = Array.isArray(tasks) ? tasks.length : 0
    }
  } catch { }
}

async function loadVolumeConfig() {
  try {
    const response = await fetch('/api/volume/status')
    if (response.ok) {
      const data = await response.json()
      snapshotsEnabled.value = data.enabled === true
    }
  } catch { }
}

async function logout() {
  await fetch('/api/logout', { method: 'POST' })
  emit('logout')
}

onMounted(() => {
  pollRunning()
  loadVolumeConfig()
  pollTimer = setInterval(pollRunning, 4000)
})
onUnmounted(() => clearInterval(pollTimer))
</script>

<template>
  <div>
    <Sidebar :header="header" :sections="sections" disableCollapse>
      <template #sidebar-item="{ item }">
        <SidebarItem :label="item.label" :icon="item.icon" :to="item.to" :isActive="isActive(item.to)">
          <template v-if="item.to === '/tasks' && runningCount > 0" #suffix>
            <span
              class="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-ink-gray-8 px-1 text-[10px] font-bold text-surface-white">
              {{ runningCount }}
            </span>
          </template>
        </SidebarItem>
      </template>
      <template #footer-items />
    </Sidebar>

    <Dialog v-model="showBenchDialog" title="Change Bench" size="sm" :showCloseButton="true">
      <template #default>
        <div class="px-4 pb-6">
          <div v-if="benches.length === 0" class="text-sm text-ink-gray-5 py-2">
            No other benches running.
          </div>
          <div v-else class="flex flex-col gap-1">
            <button
              v-for="bench in benches"
              :key="bench.port"
              class="flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-colors w-full text-left"
              :class="String(bench.port) === String(currentPort)
                ? 'bg-surface-gray-2 text-ink-gray-9 font-medium cursor-default'
                : 'text-ink-gray-7 hover:bg-surface-gray-2 cursor-pointer'"
              @click="switchBench(bench.port)"
            >
              <span>{{ bench.name }}</span>
              <LucideCheck v-if="String(bench.port) === String(currentPort)" class="h-4 w-4 text-ink-green-3" />
            </button>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>
