import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCategory,
  deactivateCategory,
  listAdminCategories,
  updateCategory,
  type AdminCategory,
} from "@/api/admin";
import { EmptyView, ErrorView, LoadingView } from "@/components/feedback/StateView";

export function AdminCategoriesPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin-categories"],
    queryFn: listAdminCategories,
  });

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-categories"] });

  return (
    <div>
      <div className="page-header">
        <h1>관리 · 카테고리</h1>
        <span className="muted small">
          NFR-07 — 재배포 없이 즉시 분류 드롭다운에 반영됩니다.
        </span>
      </div>

      <CreateForm onCreated={refresh} />

      {isLoading && <LoadingView hint="카테고리 목록을 불러오는 중…" />}
      {isError && (
        <ErrorView error={error} title="카테고리 조회 실패" onRetry={refresh} />
      )}
      {data && data.length === 0 && (
        <EmptyView
          title="등록된 카테고리가 없습니다"
          hint="위 폼에서 새 카테고리를 추가하세요."
        />
      )}
      {data && data.length > 0 && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>전체 카테고리 ({data.length}건)</h2>
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>ID</th>
                <th>code</th>
                <th>한국어 라벨</th>
                <th>영문 라벨</th>
                <th style={{ width: 60 }}>순서</th>
                <th style={{ width: 80 }}>활성</th>
                <th style={{ width: 140 }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <CategoryRow key={c.id} c={c} onChanged={refresh} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [code, setCode] = useState("");
  const [labelKo, setLabelKo] = useState("");
  const [labelEn, setLabelEn] = useState("");
  const [sortOrder, setSortOrder] = useState(0);

  const create = useMutation({
    mutationFn: () =>
      createCategory({
        code: code.trim().toUpperCase(),
        label_ko: labelKo.trim(),
        label_en: labelEn.trim() || undefined,
        sort_order: sortOrder,
      }),
    onSuccess: () => {
      setCode("");
      setLabelKo("");
      setLabelEn("");
      setSortOrder(0);
      onCreated();
    },
  });

  const valid = /^[A-Z][A-Z0-9_]+$/.test(code.trim().toUpperCase()) && labelKo.trim().length > 0;

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>새 카테고리 추가</h2>
      <div className="form-row">
        <label>
          <span>code (대문자, _ 허용)</span>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="예: COMPLIANCE_INQUIRY"
          />
        </label>
        <label>
          <span>한국어 라벨</span>
          <input
            type="text"
            value={labelKo}
            onChange={(e) => setLabelKo(e.target.value)}
            placeholder="예: 컴플라이언스 문의"
          />
        </label>
        <label>
          <span>영문 라벨 (선택)</span>
          <input
            type="text"
            value={labelEn}
            onChange={(e) => setLabelEn(e.target.value)}
            placeholder="예: Compliance Inquiry"
          />
        </label>
        <label style={{ maxWidth: 90 }}>
          <span>정렬</span>
          <input
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
            min={0}
          />
        </label>
        <button
          type="button"
          className="primary"
          disabled={!valid || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "추가 중…" : "+ 추가"}
        </button>
      </div>
      {create.isError && (
        <div className="banner err">추가 실패: {(create.error as Error).message}</div>
      )}
    </div>
  );
}

function CategoryRow({ c, onChanged }: { c: AdminCategory; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [labelKo, setLabelKo] = useState(c.label_ko);
  const [labelEn, setLabelEn] = useState(c.label_en ?? "");
  const [sortOrder, setSortOrder] = useState(c.sort_order);

  const save = useMutation({
    mutationFn: () =>
      updateCategory(c.id, {
        label_ko: labelKo,
        label_en: labelEn || undefined,
        sort_order: sortOrder,
      }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
  });
  const toggleActive = useMutation({
    mutationFn: () => updateCategory(c.id, { is_active: !c.is_active }),
    onSuccess: onChanged,
  });
  const deactivate = useMutation({
    mutationFn: () => deactivateCategory(c.id),
    onSuccess: onChanged,
  });

  return (
    <tr style={{ opacity: c.is_active ? 1 : 0.5 }}>
      <td className="mono small">{c.id}</td>
      <td className="mono small">{c.code}</td>
      <td>
        {editing ? (
          <input value={labelKo} onChange={(e) => setLabelKo(e.target.value)} />
        ) : (
          c.label_ko
        )}
      </td>
      <td>
        {editing ? (
          <input value={labelEn} onChange={(e) => setLabelEn(e.target.value)} />
        ) : (
          c.label_en ?? "—"
        )}
      </td>
      <td>
        {editing ? (
          <input
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
            style={{ width: 50 }}
          />
        ) : (
          c.sort_order
        )}
      </td>
      <td>
        <span className={`status-pill ${c.is_active ? "ok" : "err"}`}>
          {c.is_active ? "활성" : "비활성"}
        </span>
      </td>
      <td>
        {editing ? (
          <>
            <button
              type="button"
              className="primary"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              저장
            </button>
            <button type="button" onClick={() => setEditing(false)}>취소</button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => setEditing(true)}>편집</button>
            <button type="button" onClick={() => toggleActive.mutate()}>
              {c.is_active ? "비활성화" : "재활성"}
            </button>
            {c.is_active && (
              <button
                type="button"
                className="danger"
                disabled={deactivate.isPending}
                onClick={() => {
                  if (confirm(`'${c.code}' 카테고리를 비활성화할까요?`)) {
                    deactivate.mutate();
                  }
                }}
              >
                삭제
              </button>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
