import { create } from "zustand";

import {
  ApiError,
  fetchMe,
  login,
  logout as logoutRequest,
  onAuthExpired,
  register,
  setAccessToken,
  type SignUpInput,
} from "@/lib/api";
import { clearAuthCookies, setAuthCookies } from "@/lib/auth-cookies";
import type { UserPublic } from "@/types/api";

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  user: UserPublic | null;
  error: string | null;
  /** Restore the session from the refresh cookie on first load. */
  bootstrap: () => Promise<void>;
  signIn: (email: string, password: string, remember?: boolean) => Promise<UserPublic>;
  signUp: (input: SignUpInput) => Promise<UserPublic>;
  signOut: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => {
  onAuthExpired(() => {
    clearAuthCookies();
    set({ status: "unauthenticated", user: null });
  });

  return {
    status: "idle",
    user: null,
    error: null,

    bootstrap: async () => {
      if (get().status === "loading" || get().status === "authenticated") {
        return;
      }
      set({ status: "loading", error: null });
      try {
        // A dead access token is transparently refreshed by the API client.
        const user = await fetchMe();
        setAuthCookies(user.role);
        set({ status: "authenticated", user });
      } catch {
        setAccessToken(null);
        clearAuthCookies();
        set({ status: "unauthenticated", user: null });
      }
    },

    signIn: async (email, password, remember = true) => {
      set({ status: "loading", error: null });
      try {
        const tokens = await login(email, password);
        setAccessToken(tokens.access_token);
        setAuthCookies(tokens.user.role, remember);
        set({ status: "authenticated", user: tokens.user });
        return tokens.user;
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.message
            : "Sign-in failed. Please check your connection and try again.";
        set({ status: "unauthenticated", user: null, error: message });
        throw error;
      }
    },

    signUp: async (input) => {
      set({ status: "loading", error: null });
      try {
        const tokens = await register(input);
        setAccessToken(tokens.access_token);
        setAuthCookies(tokens.user.role);
        set({ status: "authenticated", user: tokens.user });
        return tokens.user;
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.message
            : "Registration failed. Please check your connection and try again.";
        set({ status: "unauthenticated", user: null, error: message });
        throw error;
      }
    },

    signOut: async () => {
      try {
        await logoutRequest();
      } catch {
        // The cookie may already be gone; clear local state regardless.
      }
      setAccessToken(null);
      clearAuthCookies();
      set({ status: "unauthenticated", user: null });
    },

    clearError: () => set({ error: null }),
  };
});
