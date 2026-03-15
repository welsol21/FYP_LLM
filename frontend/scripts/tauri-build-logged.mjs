import { spawn } from 'node:child_process'

const startedAt = Date.now()
console.log('[tauri-build] start')
const child = spawn('npx', ['tauri', 'build'], {
  stdio: 'inherit',
  shell: false,
  env: {
    ...process.env,
    RUST_MIN_STACK: process.env.RUST_MIN_STACK || '16777216',
  },
})
child.on('exit', (code) => {
  const elapsedSec = Math.round((Date.now() - startedAt) / 1000)
  if (code === 0) {
    console.log(`[tauri-build] done in ${elapsedSec}s`)
    process.exit(0)
  }
  console.error(`[tauri-build] failed in ${elapsedSec}s with code ${code}`)
  process.exit(code ?? 1)
})
