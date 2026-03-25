import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { copyFileSync, mkdirSync } from 'fs'
import { resolve } from 'path'

// Plugin to copy @ffmpeg/core files into dist so they're served locally.
// Without this the fallback URL points to cdn.jsdelivr.net.
function ffmpegCorePlugin() {
  return {
    name: 'ffmpeg-core-copy',
    writeBundle() {
      const src = resolve(__dirname, 'node_modules/@ffmpeg/core/dist/esm')
      const dest = resolve(__dirname, 'dist/ffmpeg')
      mkdirSync(dest, { recursive: true })
      for (const file of ['ffmpeg-core.js', 'ffmpeg-core.wasm']) {
        copyFileSync(resolve(src, file), resolve(dest, file))
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), ffmpegCorePlugin()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx']
  }
})
