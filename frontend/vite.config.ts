import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  base: "/akasha/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // AI prediction service (Ordering Schedule Beta) - a separate FastAPI app.
      '/akasha/ai-api': {
        target: process.env.AI_API_TARGET || 'https://d2ff-2a09-bac5-3af4-1a46-00-29e-c6.ngrok-free.app',
        changeOrigin: true,
        // ngrok's free tier serves an HTML warning page instead of the API unless this is sent.
        headers: { 'ngrok-skip-browser-warning': 'true' },
        rewrite: (p) => p.replace(/^\/akasha\/ai-api/, '/api/ai/v1'),
      },
      '/akasha/api': {
        target: 'http://localhost:3510',
        changeOrigin: true,
      }
    }
  }
})
