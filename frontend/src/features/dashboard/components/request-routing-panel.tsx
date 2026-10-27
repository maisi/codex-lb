import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccounts } from "@/features/accounts/hooks/use-accounts";
import { useRequestRouting } from "@/features/dashboard/hooks/use-request-routing";
import type { RoutingAttempt, RoutingCandidate } from "@/features/dashboard/schemas";
import { cn } from "@/lib/utils";
import { formatPercentNullable } from "@/utils/formatters";

const OWNER_FLAGS = ["budget_pressured", "rate_limit_far_away", "burn_first_reallocate", "overload_reroute"] as const;

function compareCandidates(left: RoutingCandidate, right: RoutingCandidate): number {
  const leftRank = left.rank ?? Number.MAX_SAFE_INTEGER;
  const rightRank = right.rank ?? Number.MAX_SAFE_INTEGER;
  return leftRank - rightRank || left.accountId.localeCompare(right.accountId);
}

export function RequestRoutingPanel({ requestId }: { requestId: string | null | undefined }) {
  const { t } = useTranslation();
  const routingQuery = useRequestRouting(requestId);
  const { accountsQuery } = useAccounts();
  const accountNames = useMemo(
    () => new Map((accountsQuery.data ?? []).map((account) => [account.accountId, account.email])),
    [accountsQuery.data],
  );
  const accountName = (accountId: string | null | undefined) =>
    accountId ? (accountNames.get(accountId) ?? accountId) : "—";

  if (!requestId) {
    return null;
  }

  const title = <h3 className="text-sm font-medium">{t("dashboard.requestRouting.title")}</h3>;

  if (routingQuery.isPending) {
    return (
      <section className="space-y-2">
        {title}
        <Skeleton className="h-20 w-full" />
      </section>
    );
  }

  if (routingQuery.isError) {
    return (
      <section className="space-y-2">
        {title}
        <div className="rounded-md border border-destructive/25 bg-destructive/10 p-3 text-xs text-destructive">
          {routingQuery.error instanceof Error ? routingQuery.error.message : t("dashboard.requestRouting.loadFailed")}
        </div>
      </section>
    );
  }

  const attempts = routingQuery.data?.attempts ?? [];

  return (
    <section className="space-y-2" aria-label={t("dashboard.requestRouting.title")}>
      {title}
      {attempts.length === 0 ? (
        <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
          {t("dashboard.requestRouting.unavailable")}
        </div>
      ) : (
        attempts.map((attempt) => (
          <RoutingAttemptView
            key={attempt.attempt}
            attempt={attempt}
            showAttemptNumber={attempts.length > 1}
            accountName={accountName}
          />
        ))
      )}
    </section>
  );
}

function RoutingAttemptView({
  attempt,
  showAttemptNumber,
  accountName,
}: {
  attempt: RoutingAttempt;
  showAttemptNumber: boolean;
  accountName: (accountId: string | null | undefined) => string;
}) {
  const { t } = useTranslation();
  const candidates = [...attempt.candidates].sort(compareCandidates);
  const ownerFlags = OWNER_FLAGS.filter((flag) => attempt.ownerFlags[flag]);
  const facts: string[] = [];
  if (attempt.keyRanksAccounts && attempt.servingRank !== null) {
    facts.push(t("dashboard.requestRouting.servingRank", { rank: attempt.servingRank + 1 }));
  }
  if (attempt.decidedBy) {
    facts.push(
      t("dashboard.requestRouting.decidedByLabel", {
        pass: t(`dashboard.requestRouting.decidedBy.${attempt.decidedBy}`, { defaultValue: attempt.decidedBy }),
      }),
    );
  }

  return (
    <div className="space-y-2 rounded-md border p-3">
      {showAttemptNumber ? (
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
          {t("dashboard.requestRouting.attempt", { attempt: attempt.attempt })}
        </div>
      ) : null}
      <p className="text-sm">
        {t(`dashboard.requestRouting.outcome.${attempt.outcome}`, {
          account: accountName(attempt.selectedAccountId),
          owner: accountName(attempt.stickyOwnerAccountId),
          error: attempt.errorCode ?? "—",
          defaultValue: attempt.outcome,
        })}
      </p>
      {facts.length > 0 ? <p className="text-xs text-muted-foreground">{facts.join(" · ")}</p> : null}
      {ownerFlags.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("dashboard.requestRouting.ownerFlagsLabel", {
            flags: ownerFlags.map((flag) => t(`dashboard.requestRouting.ownerFlag.${flag}`)).join(", "),
          })}
        </p>
      ) : null}
      {attempt.rankedAccountsNotOffered.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("dashboard.requestRouting.notOffered", {
            accounts: attempt.rankedAccountsNotOffered.map(accountName).join(", "),
          })}
        </p>
      ) : null}
      {attempt.excludedAccountIds.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("dashboard.requestRouting.excluded", { accounts: attempt.excludedAccountIds.map(accountName).join(", ") })}
        </p>
      ) : null}
      {candidates.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-[11px] uppercase tracking-wider text-muted-foreground/80">
              <tr>
                <th className="py-1 pr-2 font-medium">{t("dashboard.requestRouting.columns.account")}</th>
                <th className="py-1 pr-2 font-medium">{t("dashboard.requestRouting.columns.rank")}</th>
                <th className="py-1 pr-2 font-medium">{t("dashboard.requestRouting.columns.policy")}</th>
                <th className="py-1 pr-2 font-medium">{t("dashboard.requestRouting.columns.state")}</th>
                <th className="py-1 pr-2 text-right font-medium">5h</th>
                <th className="py-1 text-right font-medium">7d</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => {
                const selected = candidate.accountId === attempt.selectedAccountId;
                return (
                  <tr
                    key={candidate.accountId}
                    className={cn("border-t", selected && "bg-primary/5 font-medium")}
                    aria-current={selected ? "true" : undefined}
                  >
                    <td className="max-w-[220px] truncate py-1 pr-2" title={candidate.accountId}>
                      {accountName(candidate.accountId)}
                      {selected ? (
                        <Badge variant="secondary" className="ml-1.5 px-1.5 py-0 text-[10px]">
                          {t("dashboard.requestRouting.selected")}
                        </Badge>
                      ) : null}
                    </td>
                    <td className="py-1 pr-2 tabular-nums">{candidate.rank === null ? "—" : candidate.rank + 1}</td>
                    <td className="py-1 pr-2">
                      {t(`dashboard.requestRouting.policy.${candidate.routingPolicy}`, {
                        defaultValue: candidate.routingPolicy,
                      })}
                    </td>
                    <td className="py-1 pr-2">{candidateState(candidate, attempt.budgetThresholdPct, t)}</td>
                    <td
                      className={cn(
                        "py-1 pr-2 text-right tabular-nums",
                        candidate.overBudgetThreshold && "text-amber-700 dark:text-amber-300",
                      )}
                      title={
                        candidate.overBudgetThreshold
                          ? t("dashboard.requestRouting.overThreshold", { threshold: attempt.budgetThresholdPct })
                          : undefined
                      }
                    >
                      {formatPercentNullable(candidate.primaryUsedPercent)}
                    </td>
                    <td className="py-1 text-right tabular-nums">
                      {formatPercentNullable(candidate.secondaryUsedPercent)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function candidateState(
  candidate: RoutingCandidate,
  threshold: number,
  t: ReturnType<typeof useTranslation>["t"],
): string {
  const parts = [
    candidate.eligible
      ? t("dashboard.requestRouting.state.available")
      : t(`dashboard.requestRouting.state.${candidate.unavailableReason ?? "unavailable"}`, {
          defaultValue: candidate.unavailableReason ?? candidate.status,
        }),
  ];
  if (candidate.eligible && candidate.overBudgetThreshold) {
    parts.push(t("dashboard.requestRouting.state.over_threshold", { threshold }));
  }
  if (candidate.health !== "healthy") {
    parts.push(t(`dashboard.requestRouting.health.${candidate.health}`, { defaultValue: candidate.health }));
  }
  if (candidate.overloadBackoff) {
    parts.push(t("dashboard.requestRouting.state.overload_backoff"));
  }
  return parts.join(", ");
}
