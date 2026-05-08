import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { copyFileSync, mkdirSync, readFileSync, existsSync } from 'fs'
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
      // @ffmpeg/ffmpeg worker files — ffmpeg-worker.js is the classWorkerURL entry point;
      // const.js and errors.js are its ES module imports (resolved relative to worker URL).
      const workerSrc = resolve(__dirname, 'node_modules/@ffmpeg/ffmpeg/dist/esm')
      for (const file of ['worker.js', 'const.js', 'errors.js']) {
        copyFileSync(
          resolve(workerSrc, file),
          resolve(dest, file === 'worker.js' ? 'ffmpeg-worker.js' : file),
        )
      }
    },
  }
}

// Plugin to copy ONNX Runtime WASM files into dist so multi-threaded CPU
// inference works without CDN. Also needed in public/ for dev server.
// The configureServer hook serves /onnx/ files as raw static assets,
// bypassing Vite's module transformation which breaks .mjs dynamic imports.
function onnxWasmPlugin() {
  const onnxFiles = [
    'ort-wasm-simd-threaded.wasm',
    'ort-wasm-simd-threaded.mjs',
    'ort-wasm-simd-threaded.jsep.mjs',
    'ort-wasm-simd-threaded.jsep.wasm',
  ]
  return {
    name: 'onnx-wasm-copy',
    writeBundle() {
      const src = resolve(__dirname, 'node_modules/onnxruntime-web/dist')
      const dest = resolve(__dirname, 'dist/onnx')
      mkdirSync(dest, { recursive: true })
      for (const file of onnxFiles) {
        copyFileSync(resolve(src, file), resolve(dest, file))
      }
    },
    configureServer(server: { middlewares: { use: (fn: (req: any, res: any, next: () => void) => void) => void } }) {
      // In Vite dev mode, dynamic import() of .mjs files gets ?import appended,
      // which causes Vite's module pipeline to return the SPA HTML fallback instead
      // of the actual file. Register WITHOUT a path prefix so this middleware runs
      // first in the Connect stack, before Vite's own handlers.
      const onnxDir = resolve(__dirname, 'public/onnx')
      server.middlewares.use((req: any, res: any, next: () => void) => {
        const url: string = req.url || ''
        if (!url.startsWith('/onnx/')) { next(); return }
        const cleanPath = url.split('?')[0]
        const filePath = resolve(onnxDir, cleanPath.slice('/onnx/'.length))
        if (!filePath.startsWith(onnxDir) || !existsSync(filePath)) { next(); return }
        const ext = filePath.split('.').pop() || ''
        const mime: Record<string, string> = { wasm: 'application/wasm', mjs: 'text/javascript', js: 'text/javascript' }
        res.setHeader('Content-Type', mime[ext] || 'application/octet-stream')
        res.setHeader('Cross-Origin-Opener-Policy', 'same-origin')
        res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp')
        res.setHeader('Cross-Origin-Resource-Policy', 'same-origin')
        res.end(readFileSync(filePath))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), ffmpegCorePlugin(), onnxWasmPlugin()],
  server: {
    headers: {
      // Required for SharedArrayBuffer (FFmpeg WASM multithreading).
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': 'http://172.19.0.2:8000',
      '/uploads': 'http://172.19.0.2:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx']
  }
})
