import { create } from "zustand";
import type { User } from "@/types/api";

const FORWARDED_USER_KEY = "voc.forwardedUser";

interface AuthState {
  user: User | null;
  /** X-Forwarded-User 헤더로 보낼 email. null 이면 백엔드 dev fallback (admin@example.com) 적용. */
  forwardedUser: string | null;
  setUser: (u: User | null) => void;
  setForwardedUser: (email: string | null) => void;
}

const initialForwarded = ((): string | null => {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(FORWARDED_USER_KEY);
  } catch {
    return null;
  }
})();

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  forwardedUser: initialForwarded,
  setUser: (user) => set({ user }),
  setForwardedUser: (email) => {
    if (typeof window !== "undefined") {
      try {
        if (email) window.localStorage.setItem(FORWARDED_USER_KEY, email);
        else window.localStorage.removeItem(FORWARDED_USER_KEY);
      } catch {
        // ignore
      }
    }
    set({ forwardedUser: email });
  },
}));

export function getForwardedUser(): string | null {
  return useAuthStore.getState().forwardedUser;
}
