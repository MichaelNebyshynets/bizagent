import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Отдельный конфиг: этим тестам нужен запущенный бэкенд (см. tests/chat.e2e.test.jsx)
export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', include: ['tests/**/*.e2e.test.jsx'], testTimeout: 20000 },
})
