import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

import { RequestRoutingPanel } from "./request-routing-panel";

function candidate(overrides: Record<string, unknown>) {
  return {
    accountId: "acc_x",
    rank: null,
    routingPolicy: "normal",
    status: "active",
    health: "healthy",
    primaryUsedPercent: 10,
    secondaryUsedPercent: 20,
    overBudgetThreshold: false,
    eligible: true,
    overloadBackoff: false,
    unavailableReason: null,
    ...overrides,
  };
}

const tierFailover = {
  requestId: "req_routing",
  attempts: [
    {
      attempt: 1,
      recordedAt: "2026-10-27T11:05:40Z",
      apiKeyId: "key_1",
      model: "gpt-6.1-sol",
      routingStrategy: "capacity_weighted",
      stickyKind: "prompt_cache",
      stickyOwnerAccountId: null,
      outcome: "new_selection",
      selectedAccountId: "acc_secondary",
      servingRank: 0,
      decidedBy: "within_budget",
      ownerFlags: {},
      budgetThresholdPct: 95,
      keyRanksAccounts: true,
      excludedAccountIds: [],
      rankedAccountsNotOffered: [],
      candidates: [
        candidate({ accountId: "acc_reserve", rank: 1, routingPolicy: "burn_first" }),
        candidate({
          accountId: "acc_primary",
          rank: 0,
          routingPolicy: "burn_first",
          status: "rate_limited",
          primaryUsedPercent: 100,
          overBudgetThreshold: true,
          eligible: false,
          unavailableReason: "rate_limited",
        }),
        candidate({ accountId: "acc_secondary", rank: 0 }),
      ],
      errorCode: null,
    },
  ],
};

describe("RequestRoutingPanel", () => {
  it("says when no decision is kept for the request", async () => {
    renderWithProviders(<RequestRoutingPanel requestId="req_unknown" />);

    expect(await screen.findByText(/No routing decision recorded/)).toBeInTheDocument();
  });

  it("explains a failover inside the key's first rank", async () => {
    server.use(http.get("/api/request-logs/:requestId/routing", () => HttpResponse.json(tierFailover)));

    renderWithProviders(<RequestRoutingPanel requestId="req_routing" />);

    expect(await screen.findByText("Picked secondary@example.com for a new conversation turn.")).toBeInTheDocument();
    expect(
      screen.getByText("Served from the API key's priority rank 1 · Decided by: accounts below the budget threshold"),
    ).toBeInTheDocument();

    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    // Rank order, unranked last; the rank-0 accounts sort by id.
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual(["1", "1", "2"]);
    const primary = rows.find((row) => row.textContent?.includes("primary@example.com"));
    expect(primary).toHaveTextContent("rate-limited");
    expect(primary).toHaveTextContent("Burn first");
    const selected = rows.find((row) => row.getAttribute("aria-current") === "true");
    expect(selected).toHaveTextContent("secondary@example.com");
    expect(selected).toHaveTextContent("selected");
  });

  it("names the budget threshold when an available account was skipped for it", async () => {
    server.use(
      http.get("/api/request-logs/:requestId/routing", () =>
        HttpResponse.json({
          requestId: "req_threshold",
          attempts: [
            {
              ...tierFailover.attempts[0],
              selectedAccountId: "acc_reserve",
              servingRank: 1,
              decidedBy: "burn_first",
              candidates: [
                candidate({ accountId: "acc_secondary", rank: 0, primaryUsedPercent: 97, overBudgetThreshold: true }),
                candidate({ accountId: "acc_reserve", rank: 1, routingPolicy: "burn_first" }),
              ],
            },
          ],
        }),
      ),
    );

    renderWithProviders(<RequestRoutingPanel requestId="req_threshold" />);

    const table = await screen.findByRole("table");
    const secondary = within(table)
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("secondary@example.com"));
    expect(secondary).toHaveTextContent("available, above the 95% threshold");
  });

  it("explains why a conversation left its account", async () => {
    server.use(
      http.get("/api/request-logs/:requestId/routing", () =>
        HttpResponse.json({
          requestId: "req_moved",
          attempts: [
            {
              ...tierFailover.attempts[0],
              outcome: "moved_from_owner",
              stickyOwnerAccountId: "acc_primary",
              ownerFlags: { budget_pressured: true, burn_first_reallocate: false },
            },
          ],
        }),
      ),
    );

    renderWithProviders(<RequestRoutingPanel requestId="req_moved" />);

    expect(
      await screen.findByText(
        "Moved off the conversation's account primary@example.com to secondary@example.com.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Conversation account: above the budget threshold")).toBeInTheDocument();
  });
});
