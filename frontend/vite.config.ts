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
      const src = resolve(__dirname, 'node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.mjs')
      const dest = resolve(__dirname, 'dist/assets/ort-wasm-simd-threaded.jsep.mjs')
      if (existsSync(src)) copyFileSync(src, dest)
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
