import { create } from "zustand";

import type { AccountListSort, AccountListSortKey } from "@/features/dashboard/components/account-list";

const ACCOUNT_BURNRATE_STORAGE_KEY = "codex-lb-account-burnrate-enabled";
const ACCOUNT_VIEW_MODE_STORAGE_KEY = "codex-lb-dashboard-account-view-mode";
const ACCOUNT_LIST_SORT_STORAGE_KEY = "codex-lb-dashboard-account-list-sort";
const REQUEST_LOG_COLUMNS_STORAGE_KEY = "codex-lb-dashboard-request-log-columns-v1";

export type DashboardAccountViewMode = "cards" | "list";

export const REQUEST_LOG_COLUMN_IDS = [
  "time",
  "account",
  "plan",
  "apiKey",
  "model",
  "effort",
  "transport",
  "status",
  "ttft",
  "tps",
  "tokens",
  "cost",
  "details",
] as const;

export type RequestLogColumnId = (typeof REQUEST_LOG_COLUMN_IDS)[number];

export const DEFAULT_REQUEST_LOG_COLUMNS: RequestLogColumnId[] = REQUEST_LOG_COLUMN_IDS.filter(
  (column) => column !== "effort",
);

type DashboardPreferencesState = {
  accountBurnrateEnabled: boolean;
  accountViewMode: DashboardAccountViewMode;
  accountListSort: AccountListSort;
  requestLogColumns: RequestLogColumnId[];
  initialized: boolean;
  initializePreferences: () => void;
  setAccountBurnrateEnabled: (enabled: boolean) => void;
  setAccountViewMode: (mode: DashboardAccountViewMode) => void;
  setAccountListSort: (sort: AccountListSort) => void;
  setRequestLogColumns: (columns: RequestLogColumnId[]) => void;
};

const ACCOUNT_LIST_SORT_KEYS: AccountListSortKey[] = ["account", "status", "plan", "quota", "credits", "warmup"];

function isAccountListSortKey(value: unknown): value is AccountListSortKey {
  return typeof value === "string" && ACCOUNT_LIST_SORT_KEYS.includes(value as AccountListSortKey);
}

function isRequestLogColumnId(value: unknown): value is RequestLogColumnId {
  return typeof value === "string" && REQUEST_LOG_COLUMN_IDS.includes(value as RequestLogColumnId);
}

function readStoredAccountBurnrateEnabled(): boolean | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(ACCOUNT_BURNRATE_STORAGE_KEY);
  if (stored === "true") {
    return true;
  }
  if (stored === "false") {
    return false;
  }
  return null;
}

function readStoredAccountViewMode(): DashboardAccountViewMode | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(ACCOUNT_VIEW_MODE_STORAGE_KEY);
  return stored === "cards" || stored === "list" ? stored : null;
}

function readStoredAccountListSort(): AccountListSort {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(ACCOUNT_LIST_SORT_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  try {
    const parsed = JSON.parse(stored) as { key?: unknown; direction?: unknown };
    if (
      isAccountListSortKey(parsed.key) &&
      (parsed.direction === "asc" || parsed.direction === "desc")
    ) {
      return { key: parsed.key, direction: parsed.direction };
    }
  } catch {
    return null;
  }
  return null;
}

function persistAccountBurnrateEnabled(enabled: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACCOUNT_BURNRATE_STORAGE_KEY, String(enabled));
}

function persistAccountViewMode(mode: DashboardAccountViewMode): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACCOUNT_VIEW_MODE_STORAGE_KEY, mode);
}

function persistAccountListSort(sort: AccountListSort): void {
  if (typeof window === "undefined") {
    return;
  }
  if (sort === null) {
    window.localStorage.removeItem(ACCOUNT_LIST_SORT_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(ACCOUNT_LIST_SORT_STORAGE_KEY, JSON.stringify(sort));
}

function readStoredRequestLogColumns(): RequestLogColumnId[] | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = window.localStorage.getItem(REQUEST_LOG_COLUMNS_STORAGE_KEY);
    if (!stored) {
      return null;
    }
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) {
      return null;
    }
    const columns = [...new Set(parsed.filter(isRequestLogColumnId))];
    return columns.length > 0 ? columns : null;
  } catch {
    return null;
  }
}

function persistRequestLogColumns(columns: RequestLogColumnId[]): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(REQUEST_LOG_COLUMNS_STORAGE_KEY, JSON.stringify(columns));
  } catch {
    // Storage can be unavailable in restricted browser contexts; keep the in-memory preference usable.
  }
}

export const useDashboardPreferencesStore = create<DashboardPreferencesState>((set) => ({
  accountBurnrateEnabled: true,
  accountViewMode: "cards",
  accountListSort: null,
  requestLogColumns: DEFAULT_REQUEST_LOG_COLUMNS,
  initialized: false,
  initializePreferences: () => {
    const accountBurnrateEnabled = readStoredAccountBurnrateEnabled() ?? true;
    const accountViewMode = readStoredAccountViewMode() ?? "cards";
    const accountListSort = readStoredAccountListSort();
    const requestLogColumns = readStoredRequestLogColumns() ?? DEFAULT_REQUEST_LOG_COLUMNS;
    persistAccountBurnrateEnabled(accountBurnrateEnabled);
    persistAccountViewMode(accountViewMode);
    persistAccountListSort(accountListSort);
    persistRequestLogColumns(requestLogColumns);
    set({ accountBurnrateEnabled, accountViewMode, accountListSort, requestLogColumns, initialized: true });
  },
  setAccountBurnrateEnabled: (enabled) => {
    persistAccountBurnrateEnabled(enabled);
    set({ accountBurnrateEnabled: enabled, initialized: true });
  },
  setAccountViewMode: (mode) => {
    persistAccountViewMode(mode);
    set({ accountViewMode: mode, initialized: true });
  },
  setAccountListSort: (sort) => {
    persistAccountListSort(sort);
    set({ accountListSort: sort, initialized: true });
  },
  setRequestLogColumns: (columns) => {
    const requestLogColumns = columns.length > 0 ? columns : DEFAULT_REQUEST_LOG_COLUMNS;
    persistRequestLogColumns(requestLogColumns);
    set({ requestLogColumns, initialized: true });
  },
}));
