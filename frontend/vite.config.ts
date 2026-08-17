import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // This proxy is used by `vite dev` only; production uses VITE_API_BASE_URL
        // or the reverse proxy defined in nginx.conf.
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
