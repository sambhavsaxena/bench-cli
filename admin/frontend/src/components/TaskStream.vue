<script setup>
// Streams a task's output (SSE) into a terminal. Owns the EventSource lifecycle
// via useTaskStream; renders a plain TerminalOutput by default, or hands the
// reactive stream state to a scoped slot for custom layouts (e.g. a step view).
//
// The stream is driven by the reactive `url` prop: set it (or change it) and the
// component (re)connects. Collapsing/showing the terminal is the parent's job —
// keep this component mounted (e.g. v-show) so streaming continues while hidden.
import { onMounted, watch } from 'vue'
import TerminalOutput from './TerminalOutput.vue'
import { useTaskStream } from '../composables/useTaskStream.js'
import { processLine } from '../utils/ansi.js'

const props = defineProps({
  url: { type: String, default: '' },
  autoStart: { type: Boolean, default: true },   // connect as soon as url is present
  reset: { type: Boolean, default: true },         // clear prior output on each (re)start
  initialLines: { type: Array, default: () => [] }, // seed before streaming (REST pre-load)
  guardHiddenTab: { type: Boolean, default: false },
  // passthrough to the default TerminalOutput (ignored when a slot is provided)
  lineNumbers: { type: Boolean, default: false },
  emptyText: { type: String, default: 'No output yet…' },
  maxHeight: { type: String, default: '65vh' },
})
const emit = defineEmits(['line', 'done', 'error'])

const stream = useTaskStream({ guardHiddenTab: props.guardHiddenTab })
const { terminal, lines, rawLines, streaming } = stream

// Bind a slot-rendered terminal as the scroll target (the default terminal binds
// itself via ref="terminal").
const setTerminal = (el) => { terminal.value = el }

function seed(initial) {
  rawLines.value = [...initial]
  lines.value = initial.map(processLine)
}

function start(url = props.url) {
  if (!url) return
  if (props.reset) { rawLines.value = []; lines.value = [] }
  stream.start(url, {
    onLine: (raw) => emit('line', raw),
    onDone: (success) => emit('done', success),
    onError: () => emit('error'),
  })
}

onMounted(() => {
  if (props.initialLines.length) seed(props.initialLines)
  if (props.autoStart && props.url) start()
})

// React to url changes — e.g. Setup's init → production sequence, or a url set
// after an async pre-load. onMounted covers the first connect, so guard against
// re-firing for the same value.
watch(() => props.url, (url, prev) => {
  if (props.autoStart && url && url !== prev) start(url)
})

defineExpose({ start, stop: stream.stop, scrollToBottom: stream.scrollToBottom, seed, lines, rawLines, streaming })
</script>

<template>
  <slot
    :lines="lines"
    :raw-lines="rawLines"
    :streaming="streaming"
    :set-terminal="setTerminal"
    :scroll-to-bottom="stream.scrollToBottom"
  >
    <TerminalOutput
      ref="terminal"
      :lines="lines"
      :streaming="streaming"
      :line-numbers="lineNumbers"
      :empty-text="emptyText"
      :max-height="maxHeight"
    />
  </slot>
</template>
