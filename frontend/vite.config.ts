import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard calls the FastAPI backend directly at http://localhost:8000
// (see src/api.ts); the backend's CORS settings allow this page's origin.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
})
