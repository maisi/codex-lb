import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { AlertMessage } from "@/components/alert-message";
import { Button } from "@/components/ui/button";
import { grantedScope, useAuthStore } from "@/features/auth/hooks/use-auth";
import { get, post } from "@/lib/api-client";

const path = "/api/runtime/oracle-storage";
const queryKey = ["runtime", "oracle-storage"];
const statusSchema = z.object({
  level: z.enum(["healthy", "warning", "critical", "unavailable"]),
  freeBytes: z.number().nullable(),
  maintenance: z.enum(["idle", "queued", "running", "completed", "no_space", "no_gain", "failed"]),
});

export function OracleStorageNotice() {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const canRead = useAuthStore((s) => grantedScope(s.permissions, "dashboard:read") === "all");
  const canManage = useAuthStore((s) => grantedScope(s.permissions, "ops:write") === "all");
  const status = useQuery({
    queryKey,
    enabled: canRead,
    queryFn: () => get(path, statusSchema.nullable()),
    refetchInterval: ({ state }) => {
      if (state.data === null) return false;
      return state.data?.level === "healthy" ? 60_000 : 10_000;
    },
  });
  const run = useMutation({
    mutationFn: () => post(path + "/maintenance", statusSchema),
    onSuccess: (data) => client.setQueryData(queryKey, data),
  });
  const data = status.data;
  if (!canRead || !data || data.level === "healthy") return null;

  const busy = data.maintenance === "queued" || data.maintenance === "running";
  const free = data.freeBytes === null ? "" : (data.freeBytes / 2 ** 30).toLocaleString(i18n.language, {
    maximumFractionDigits: 2,
  });
  return (
    <section aria-live="polite" aria-label={t("dashboard.oracleStorage.title")}>
      <AlertMessage variant={data.level === "warning" ? "warning" : "error"}>
        <strong>{t("dashboard.oracleStorage.title")}</strong>{" "}
        {data.level === "unavailable"
          ? t("dashboard.oracleStorage.unavailable")
          : t("dashboard.oracleStorage.free", { free })}
        {data.level !== "unavailable" && (
          <span className="mt-1 block">
            {t(`dashboard.oracleStorage.${data.maintenance === "idle" ? data.level : data.maintenance}`)}
          </span>
        )}
        {canManage && data.level === "warning" && !busy && (
          <Button className="mt-2" size="sm" variant="outline" disabled={run.isPending} onClick={() => run.mutate()}>
            {t("dashboard.oracleStorage.action")}
          </Button>
        )}
        {run.isError && <span role="alert" className="mt-1 block">{t("dashboard.oracleStorage.requestFailed")}</span>}
      </AlertMessage>
    </section>
  );
}
