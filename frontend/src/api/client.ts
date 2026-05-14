import axios from "axios";
import { getForwardedUser } from "@/stores/authStore";

const baseURL = import.meta.env.VITE_API_BASE || "";

export const api = axios.create({
  baseURL,
  withCredentials: false,
  timeout: 15_000,
});

// Phase 7.1 — X-Forwarded-User 헤더 자동 부착. PoC 인증 모델.
api.interceptors.request.use((config) => {
  const email = getForwardedUser();
  if (email) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)["X-Forwarded-User"] = email;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response) {
      const { status, data } = err.response;
      console.warn("[api] error", status, data);
    } else {
      console.warn("[api] network error", err?.message);
    }
    return Promise.reject(err);
  }
);
