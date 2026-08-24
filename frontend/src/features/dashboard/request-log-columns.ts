export const REQUEST_LOG_COLUMN_OPTIONS = [
  { id: "time", translationKey: "dashboard.requests.columns.time" },
  { id: "account", translationKey: "dashboard.requests.columns.account" },
  { id: "plan", translationKey: "dashboard.requests.columns.plan" },
  { id: "apiKey", translationKey: "dashboard.requests.columns.apiKey" },
  { id: "model", translationKey: "dashboard.requests.columns.model" },
  { id: "effort", translationKey: "dashboard.requests.columns.effort" },
  { id: "transport", translationKey: "dashboard.requests.columns.transport" },
  { id: "status", translationKey: "dashboard.requests.columns.status" },
  { id: "ttft", translationKey: "dashboard.requests.columns.ttft" },
  { id: "tps", translationKey: "dashboard.requests.columns.tps" },
  { id: "tokens", translationKey: "dashboard.requests.columns.tokens" },
  { id: "cost", translationKey: "dashboard.requests.columns.cost" },
  { id: "details", translationKey: "dashboard.requests.columns.details" },
] as const;

export type RequestLogColumnId = (typeof REQUEST_LOG_COLUMN_OPTIONS)[number]["id"];

export const ALL_REQUEST_LOG_COLUMNS: readonly RequestLogColumnId[] =
  REQUEST_LOG_COLUMN_OPTIONS.map((column) => column.id);

// "effort" is opt-in: showing it moves the reasoning effort out of the model
// label into its own column, so the default layout leaves it off.
export const DEFAULT_REQUEST_LOG_COLUMNS: readonly RequestLogColumnId[] =
  ALL_REQUEST_LOG_COLUMNS.filter((column) => column !== "effort");

export const MIN_REQUEST_LOG_COLUMN_WIDTH = 64;
export const MAX_REQUEST_LOG_COLUMN_WIDTH = 720;
export const REQUEST_LOG_COLUMN_WIDTH_STEP = 8;

export type RequestLogColumnWidths = Partial<Record<RequestLogColumnId, number>>;

export const REQUEST_LOG_COLUMN_DEFAULT_WIDTHS: Record<RequestLogColumnId, number> = {
  time: 112,
  account: 160,
  plan: 96,
  apiKey: 144,
  model: 180,
  effort: 96,
  transport: 128,
  status: 96,
  ttft: 80,
  tps: 80,
  tokens: 96,
  cost: 64,
  details: 288,
};

export function clampRequestLogColumnWidth(width: number): number {
  return Math.round(
    Math.max(MIN_REQUEST_LOG_COLUMN_WIDTH, Math.min(MAX_REQUEST_LOG_COLUMN_WIDTH, width)),
  );
}
