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
      // AI prediction service (Ordering Schedule Beta) - a separate FastAPI app (Ordering_Schedule_AI/).
      '/akasha/ai-api': {
        target: process.env.AI_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/akasha\/ai-api/, '/api/ai/v1'),
      },
      '/akasha/api': {
        target: 'http://localhost:3510',
        changeOrigin: true,
      }
    }
  }
})
