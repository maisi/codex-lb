import { useTranslation } from "react-i18next";

import type { ApiKeyCacheEntry } from "../schemas";

export type ApiKeyCacheUsageProps = {
  data: ApiKeyCacheEntry[];
};

export function ApiKeyCacheUsage({ data }: ApiKeyCacheUsageProps) {
  const { t } = useTranslation();

  return (
    <section className="rounded-xl border bg-card p-5">
      <h2 className="text-sm font-semibold text-foreground">
        {t("reports.apiKeyCache.title")}
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">
        {t("reports.apiKeyCache.description")}
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="pb-2 font-medium">{t("reports.apiKeyCache.apiKey")}</th>
              <th className="pb-2 text-right font-medium">{t("reports.apiKeyCache.input")}</th>
              <th className="pb-2 text-right font-medium">{t("reports.apiKeyCache.cached")}</th>
              <th className="pb-2 text-right font-medium">{t("reports.apiKeyCache.hitRatio")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((entry) => (
              <tr key={entry.apiKeyId ?? "unattributed"} className="border-t">
                <td className="py-2 font-mono text-xs text-foreground">
                  {entry.apiKeyName
                    ? `${entry.apiKeyName}${entry.keyPrefix ? ` (${entry.keyPrefix}...)` : ""}`
                    : entry.apiKeyId ?? t("reports.apiKeyCache.unattributed")}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {entry.totalInputTokens.toLocaleString()}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {entry.cachedInputTokens.toLocaleString()}
                </td>
                <td className="py-2 text-right tabular-nums">
                  {(entry.cacheHitRatio * 100).toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
