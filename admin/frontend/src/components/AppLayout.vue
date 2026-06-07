<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { Breadcrumbs } from 'frappe-ui'
import AppSidebar from './AppSidebar.vue'

const emit = defineEmits(['logout'])

const route = useRoute()

const breadcrumbs = computed(() => {
  const { path, params } = route

  if (path === '/') return [{ label: 'Dashboard' }]
  if (path === '/apps') return [{ label: 'Apps' }]
  if (path === '/sites') return [{ label: 'Sites' }]
  if (path.startsWith('/sites/')) return [
    { label: 'Sites', route: '/sites' },
    { label: String(params.name) },
  ]
  if (path === '/processes') return [{ label: 'Processes' }]
  if (path === '/logs') return [{ label: 'Logs' }]
  if (path.startsWith('/logs/')) return [
    { label: 'Logs', route: '/logs' },
    { label: String(params.filename) },
  ]
  if (path === '/tasks') return [{ label: 'Tasks' }]
  if (path.startsWith('/tasks/')) return [
    { label: 'Tasks', route: '/tasks' },
    { label: String(params.id) },
  ]
  if (path === '/database') return [{ label: 'Database' }]
  if (path.startsWith('/database/binlogs/')) return [
    { label: 'Database' },
    { label: 'Binary Logs', route: '/database/binlogs' },
    { label: String(params.name) },
  ]
  if (path === '/settings') return [{ label: 'Settings' }]
  return [{ label: '' }]
})
</script>

<template>
  <div class="flex h-screen overflow-hidden">
    <AppSidebar @logout="$emit('logout')" />
    <main class="flex-1 overflow-auto bg-surface-white">
      <header class="sticky top-0 z-[10] flex items-center border-b bg-surface-white px-5 py-2.5">
        <Breadcrumbs :items="breadcrumbs" />
        <div id="header-actions" class="ml-auto flex items-center gap-2" />
      </header>
      <div class="p-6">
        <RouterView />
      </div>
    </main>
  </div>
</template>
