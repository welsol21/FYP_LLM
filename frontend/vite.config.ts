import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { copyFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

// ONNX Runtime dynamically imports this .mjs file at runtime from the same
// directory as the main bundle. Vite doesn't bundle it automatically, so we
// copy it from node_modules into dist/assets after each build.
function copyOnnxJsep() {
  return {
    name: 'copy-onnx-jsep',
    writeBundle() {
      const distAssets = resolve(__dirname, 'dist/assets')
      const onnxDist = resolve(__dirname, 'node_modules/onnxruntime-web/dist')
      for (const f of [
        'ort-wasm-simd-threaded.jsep.mjs',
        'ort-wasm-simd-threaded.jsep.wasm',
      ]) {
        const src = resolve(onnxDist, f)
        if (existsSync(src)) copyFileSync(src, resolve(distAssets, f))
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), copyOnnxJsep()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx']
  }
})
