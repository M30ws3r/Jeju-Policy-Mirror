import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 로컬 개발도 HTTPS: backend/scripts/gen_dev_cert.py 가 만든 인증서가 있으면 사용한다.
const certDir = resolve(__dirname, "../backend/certs");
const hasCert = existsSync(resolve(certDir, "localhost.pem"));

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    https: hasCert
      ? { cert: readFileSync(resolve(certDir, "localhost.pem")), key: readFileSync(resolve(certDir, "localhost-key.pem")) }
      : undefined,
    // /api 를 같은 출처로 프록시 → 쿠키는 SameSite=Lax 로 충분하고 CORS 예외가 필요 없다.
    proxy: {
      "/api": { target: hasCert ? "https://localhost:8000" : "http://localhost:8000", changeOrigin: true, secure: false },
    },
  },
});
