import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Прокси настраивается внутри server: на верхнем уровне конфига Vite его молча игнорирует.
// Сейчас компоненты ходят на http://localhost:8000 напрямую (CORS разрешён на бэкенде),
// а прокси пригодится, если перейти на относительные пути вида '/agent/...'.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://localhost:8000',
      '/agent': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
