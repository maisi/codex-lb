import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { createAccountSummary } from "@/test/mocks/factories";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

import { AccountMultiSelect } from "./account-multi-select";

describe("AccountMultiSelect", () => {
  it("shows available account limits inside the picker", async () => {
    server.use(
      http.get("/api/accounts", () =>
        HttpResponse.json({
          accounts: [
            createAccountSummary({
              accountId: "acc_quota",
              email: "quota@example.com",
              displayName: "Quota account",
              usage: {
                primaryRemainingPercent: 82,
                secondaryRemainingPercent: 67,
              },
            }),
          ],
        }),
      ),
    );

    const user = userEvent.setup();

    renderWithProviders(<AccountMultiSelect value={[]} onChange={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "All accounts" }));

    expect(await screen.findByText("5h 82% left")).toBeInTheDocument();
    expect(screen.getByText("7d 67% left")).toBeInTheDocument();
    expect(screen.queryByText(/GPT-5\.3-Codex-Spark/i)).not.toBeInTheDocument();
  });

  it("keeps account selection working with the richer rows", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(<AccountMultiSelect value={[]} onChange={onChange} />);

    await user.click(await screen.findByRole("button", { name: "All accounts" }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: /primary@example\.com/i }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(["acc_primary"]);
    });
  });

  it("pluralizes the selected account count", async () => {
    renderWithProviders(
      <AccountMultiSelect value={["acc_primary", "acc_secondary"]} onChange={vi.fn()} />,
    );

    expect(await screen.findByRole("button", { name: "2 accounts selected" })).toBeInTheDocument();
  });

  it("excludes hard-blocked accounts from new selections", async () => {
    server.use(
      http.get("/api/accounts", () =>
        HttpResponse.json({
          accounts: [
            createAccountSummary({
              accountId: "acc_active_picker",
              email: "active-picker@example.com",
              displayName: "Active picker",
            }),
            createAccountSummary({
              accountId: "acc_reauth_picker",
              email: "reauth-picker@example.com",
              displayName: "Reauth picker",
              status: "reauth_required",
            }),
            createAccountSummary({
              accountId: "acc_paused_picker",
              email: "paused-picker@example.com",
              displayName: "Paused picker",
              status: "paused",
            }),
            createAccountSummary({
              accountId: "acc_deactivated_picker",
              email: "deactivated-picker@example.com",
              displayName: "Deactivated picker",
              status: "deactivated",
            }),
          ],
        }),
      ),
    );

    const user = userEvent.setup();

    renderWithProviders(<AccountMultiSelect value={["acc_reauth_picker"]} onChange={vi.fn()} />);

    expect(await screen.findByText("reauth-picker@example.com")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "1 account selected" }));

    expect(await screen.findByRole("menuitemcheckbox", { name: /active-picker@example\.com/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitemcheckbox", { name: /reauth-picker@example\.com/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitemcheckbox", { name: /paused-picker@example\.com/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitemcheckbox", { name: /deactivated-picker@example\.com/i })).not.toBeInTheDocument();
  });

  it("can include paused accounts while keeping other hard-blocked accounts hidden", async () => {
    server.use(
      http.get("/api/accounts", () =>
        HttpResponse.json({
          accounts: [
            createAccountSummary({
              accountId: "acc_paused_picker",
              email: "paused-picker@example.com",
              displayName: "Paused picker",
              status: "paused",
            }),
            createAccountSummary({
              accountId: "acc_reauth_picker",
              email: "reauth-picker@example.com",
              displayName: "Reauth picker",
              status: "reauth_required",
            }),
            createAccountSummary({
              accountId: "acc_deactivated_picker",
              email: "deactivated-picker@example.com",
              displayName: "Deactivated picker",
              status: "deactivated",
            }),
          ],
        }),
      ),
    );

    const user = userEvent.setup();

    renderWithProviders(<AccountMultiSelect value={[]} onChange={vi.fn()} allowPausedAccounts />);

    await user.click(await screen.findByRole("button", { name: "All accounts" }));

    expect(await screen.findByRole("menuitemcheckbox", { name: /paused-picker@example\.com/i })).toBeInTheDocument();
    expect(screen.queryByRole("menuitemcheckbox", { name: /reauth-picker@example\.com/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitemcheckbox", { name: /deactivated-picker@example\.com/i })).not.toBeInTheDocument();
  });

  it("shows Monthly left for monthly-only free accounts", async () => {
    server.use(
      http.get("/api/accounts", () =>
        HttpResponse.json({
          accounts: [
            createAccountSummary({
              accountId: "acc_free",
              email: "free@example.com",
              displayName: "Free monthly",
              planType: "free",
              usage: {
                primaryRemainingPercent: null,
                secondaryRemainingPercent: null,
                monthlyRemainingPercent: 95,
              },
              windowMinutesPrimary: null,
              windowMinutesSecondary: null,
              windowMinutesMonthly: 43_200,
            }),
          ],
        }),
      ),
    );

    const user = userEvent.setup();

    renderWithProviders(<AccountMultiSelect value={[]} onChange={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "All accounts" }));

    expect(await screen.findByText("Monthly 95% left")).toBeInTheDocument();
    expect(screen.queryByText(/7d .* left/i)).not.toBeInTheDocument();
  });
});

describe("AccountMultiSelect priority order", () => {
  it("lists the selection as a ranked order", async () => {
    renderWithProviders(
      <AccountMultiSelect
        value={["acc_secondary", "acc_primary"]}
        onChange={vi.fn()}
        showPriorityOrder
      />,
    );

    expect(await screen.findByText("Selection priority")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    // Rank follows the value order, not the account list order.
    expect(rows[0]).toHaveTextContent("1");
    expect(rows[0]).toHaveTextContent("secondary@example.com");
    expect(rows[1]).toHaveTextContent("2");
    expect(rows[1]).toHaveTextContent("primary@example.com");
  });

  it("moves an account down by swapping it with its successor", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(
      <AccountMultiSelect
        value={["acc_primary", "acc_secondary"]}
        onChange={onChange}
        showPriorityOrder
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Move primary@example.com down" }));

    expect(onChange).toHaveBeenCalledWith(["acc_secondary", "acc_primary"]);
  });

  it("moves an account up by swapping it with its predecessor", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(
      <AccountMultiSelect
        value={["acc_primary", "acc_secondary"]}
        onChange={onChange}
        showPriorityOrder
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Move secondary@example.com up" }));

    expect(onChange).toHaveBeenCalledWith(["acc_secondary", "acc_primary"]);
  });

  it("disables the moves that would fall off either end", async () => {
    renderWithProviders(
      <AccountMultiSelect
        value={["acc_primary", "acc_secondary"]}
        onChange={vi.fn()}
        showPriorityOrder
      />,
    );

    expect(await screen.findByRole("button", { name: "Move primary@example.com up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move secondary@example.com down" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move primary@example.com down" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move secondary@example.com up" })).toBeEnabled();
  });

  it("removes the account the control names", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(
      <AccountMultiSelect
        value={["acc_primary", "acc_secondary"]}
        onChange={onChange}
        showPriorityOrder
      />,
    );

    await user.click(await screen.findByRole("button", { name: "Remove primary@example.com" }));

    expect(onChange).toHaveBeenCalledWith(["acc_secondary"]);
  });

  it("keeps an assignment whose account is gone visible and removable", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    renderWithProviders(
      <AccountMultiSelect value={["acc_deleted"]} onChange={onChange} showPriorityOrder />,
    );

    // Falls back to the raw id so a stale assignment can still be cleared.
    expect(await screen.findByText("acc_deleted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove acc_deleted" }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("stays an unordered set for callers that do not opt in", async () => {
    renderWithProviders(
      <AccountMultiSelect value={["acc_primary", "acc_secondary"]} onChange={vi.fn()} />,
    );

    expect(await screen.findByRole("button", { name: "2 accounts selected" })).toBeInTheDocument();
    expect(screen.queryByText("Selection priority")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Move / })).not.toBeInTheDocument();
  });
});
