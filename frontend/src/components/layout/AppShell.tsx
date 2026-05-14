import { useEffect } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";
import type { HealthResponse, User } from "@/types/api";

export function AppShell() {
  const setUser = useAuthStore((s) => s.setUser);
  const user = useAuthStore((s) => s.user);
  const forwardedUser = useAuthStore((s) => s.forwardedUser);
  const setForwardedUser = useAuthStore((s) => s.setForwardedUser);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await api.get<HealthResponse>("/health")).data,
    refetchInterval: 30_000,
  });

  useEffect(() => {
    api.get<User>("/api/me").then((r) => setUser(r.data)).catch(() => setUser(null));
  }, [setUser, forwardedUser]);

  const isAdmin = user?.role === "ADMIN";

  const switchUser = (email: string | null) => {
    setForwardedUser(email);
    qc.clear();
    if (!email || !isAdminEmail(email)) {
      // ADMIN → OPERATOR 전환 시 admin 경로면 티켓 목록으로
      if (location.pathname.startsWith("/admin")) navigate("/tickets");
    }
  };

  return (
    <div className="app-shell">
      <header>
        <span style={{ marginRight: 16 }}>AI VOC 운영 콘솔</span>
        <span className={`status-pill ${health?.status === "ok" ? "ok" : "warn"}`}>
          {health ? `mode: ${health.integration_mode}` : "연결 중…"}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <span className="muted small">
            {user ? `${user.name} · ${user.role}` : "비로그인"}
          </span>
          {/* PoC 사용자 전환 (X-Forwarded-User 시뮬레이션). Production 에서는 reverse proxy 가 자동 세팅 */}
          <select
            className="select"
            style={{ width: "auto", fontSize: 12, padding: "4px 6px" }}
            value={forwardedUser ?? ""}
            onChange={(e) => switchUser(e.target.value || null)}
            title="X-Forwarded-User 헤더 시뮬레이션 (PoC). 빈 값이면 백엔드 dev fallback 적용."
          >
            <option value="">자동 (dev fallback)</option>
            <option value="admin@example.com">admin@example.com (ADMIN)</option>
            <option value="operator@example.com">operator@example.com (OPERATOR)</option>
          </select>
        </div>
      </header>
      <aside>
        <nav>
          <NavLink to="/tickets">티켓</NavLink>
          <NavLink to="/kpi">KPI 대시보드</NavLink>
          {isAdmin && (
            <>
              <NavLink to="/admin/categories">관리 · 카테고리</NavLink>
              <NavLink to="/admin/prompts">관리 · 프롬프트</NavLink>
            </>
          )}
        </nav>
      </aside>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

function isAdminEmail(email: string): boolean {
  return email.startsWith("admin@");
}
