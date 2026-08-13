import react from '@vitejs/plugin-react'
// 'vite'ではなく'vitest/config'から読む（Vitest公式の方法）。'vite'のdefineConfigは
// `test`キー（Vitestの設定拡張）を型として知らず、tsc -bで型エラーになるため
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
  },
})
