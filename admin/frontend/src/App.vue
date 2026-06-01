<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from './components/AppLayout.vue'
import Login from './pages/Login.vue'
import { Alert } from 'frappe-ui'

const adminEnabled = ref(true)
const adminError = ref('')
const authenticated = ref(true)
const passwordRequired = ref(false)
const benchName = ref('')

async function loadStatus() {
  const response = await fetch('/api/status')
  const data = await response.json()
  adminEnabled.value = data.enabled !== false
  authenticated.value = data.authenticated !== false
  passwordRequired.value = data.password_required === true
  benchName.value = data.name ?? ''
  if (!adminEnabled.value) {
    adminError.value = data.error || 'Admin is disabled in bench.toml'
  }
}

onMounted(async () => {
  try {
    await loadStatus()
  } catch {
    adminError.value = 'Could not reach the bench admin server.'
  }
})
</script>

<template>
  <div v-if="adminError" class="flex h-screen items-center justify-center p-8">
    <Alert theme="red" title="Admin Unavailable" :description="adminError" />
  </div>
  <Login v-else-if="!authenticated" :bench-name="benchName" @authenticated="authenticated = true" />
  <AppLayout v-else :password-required="passwordRequired" @logout="authenticated = false" />
</template>
