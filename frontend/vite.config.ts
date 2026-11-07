import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` serves the board on http://localhost:5173 and opens it in the browser.
// The board calls the FastAPI backend directly (VITE_API_URL, default http://localhost:8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    open: true,
  },
})
