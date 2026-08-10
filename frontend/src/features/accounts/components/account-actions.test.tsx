import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccountActions } from "@/features/accounts/components/account-actions";
import { createAccountSummary } from "@/test/mocks/factories";

describe("AccountActions", () => {
  it("renders an explicit routing policy selector", async () => {
    const onRoutingPolicyChange = vi.fn();
    const account = createAccountSummary({ routingPolicy: "normal" });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={vi.fn()}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={onRoutingPolicyChange}
      />,
    );

    expect(screen.getByText("Routing policy")).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Routing policy" }),
    ).toHaveTextContent("Normal");
  });

  it("renders re-authenticate action for re-auth required accounts", () => {
    const onReauth = vi.fn();
    const account = createAccountSummary({ status: "reauth_required" });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={vi.fn()}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={onReauth}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Re-authenticate" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Pause" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Routing policy" }),
    ).not.toBeInTheDocument();
  });

  it("recovers a remote reauth_required account via Force Probe (labeled Recover) and hides Re-authenticate", async () => {
    const user = userEvent.setup();
    const onProbe = vi.fn();
    const onReauth = vi.fn();
    const account = createAccountSummary({ status: "reauth_required", remote: true });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={onProbe}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={onReauth}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    // Re-authenticate is hidden for a remote account (it would create a second
    // rotating token owner); recovery is a vend check via Force Probe.
    expect(
      screen.queryByRole("button", { name: "Re-authenticate" }),
    ).not.toBeInTheDocument();
    const recover = screen.getByRole("button", { name: "Recover" });
    expect(recover).toBeEnabled();
    await user.click(recover);
    expect(onProbe).toHaveBeenCalledWith(account.accountId);
    expect(onReauth).not.toHaveBeenCalled();
  });

  it("enables Recover for a remote deactivated account", () => {
    const account = createAccountSummary({ status: "deactivated", remote: true });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={vi.fn()}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Recover" })).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Re-authenticate" }),
    ).not.toBeInTheDocument();
  });

  it("fires the per-account probe callback for active accounts", async () => {
    const user = userEvent.setup();
    const account = createAccountSummary();
    const onProbe = vi.fn();

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={onProbe}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Force probe" }));

    expect(onProbe).toHaveBeenCalledWith(account.accountId);
    expect(onProbe).toHaveBeenCalledTimes(1);
  });

  it("keeps warm now distinct from force probe for active accounts", async () => {
    const user = userEvent.setup();
    const account = createAccountSummary();
    const onProbe = vi.fn();
    const onWarmup = vi.fn();

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={onProbe}
        onWarmup={onWarmup}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Warm now" }));

    expect(onWarmup).toHaveBeenCalledWith(account.accountId);
    expect(onProbe).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Force probe" })).toBeEnabled();
  });

  it.each([
    ["paused", false, false],
    ["deactivated", false, false],
    ["reauth_required", false, false],
    ["rate_limited", false, false],
    ["active", true, false],
    ["active", false, true],
  ] as const)(
    "disables warm now for status=%s readOnly=%s busy=%s",
    async (status, readOnly, busy) => {
      const user = userEvent.setup();
      const onWarmup = vi.fn();
      render(
        <AccountActions
          account={createAccountSummary({ status })}
          busy={busy}
          readOnly={readOnly}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onProbe={vi.fn()}
          onWarmup={onWarmup}
          onDelete={vi.fn()}
          onReauth={vi.fn()}
          onExportAuth={vi.fn()}
          onResetCredit={vi.fn()}
          onSecurityWorkAuthorizedChange={vi.fn()}
          onLimitWarmupChange={vi.fn()}
          onRoutingPolicyChange={vi.fn()}
        />,
      );

      const button = screen.getByRole("button", { name: "Warm now" });
      expect(button).toBeDisabled();
      await user.click(button);
      expect(onWarmup).not.toHaveBeenCalled();
    },
  );

  it.each(["paused", "deactivated"] as const)(
    "disables force probe for %s accounts",
    async (status) => {
      const user = userEvent.setup();
      const account = createAccountSummary({ status });
      const onProbe = vi.fn();

      render(
        <AccountActions
          account={account}
          busy={false}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onProbe={onProbe}
          onWarmup={vi.fn()}
          onDelete={vi.fn()}
          onReauth={vi.fn()}
          onExportAuth={vi.fn()}
          onResetCredit={vi.fn()}
          onSecurityWorkAuthorizedChange={vi.fn()}
          onLimitWarmupChange={vi.fn()}
          onRoutingPolicyChange={vi.fn()}
        />,
      );

      const button = screen.getByRole("button", { name: "Force probe" });
      expect(button).toBeDisabled();

      await user.click(button);

      expect(onProbe).not.toHaveBeenCalled();
    },
  );

  it("enables force probe for usage 404 deactivated accounts", async () => {
    const user = userEvent.setup();
    const account = createAccountSummary({
      status: "deactivated",
      deactivationReason: "Usage API error: HTTP 404 - None",
    });
    const onProbe = vi.fn();

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={onProbe}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    const button = screen.getByRole("button", { name: "Force probe" });
    expect(button).toBeEnabled();

    await user.click(button);

    expect(onProbe).toHaveBeenCalledWith(account.accountId);
  });

  it("disables force probe in read-only mode", async () => {
    const user = userEvent.setup();
    const account = createAccountSummary();
    const onProbe = vi.fn();

    render(
      <AccountActions
        account={account}
        busy={false}
        readOnly
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={onProbe}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    const button = screen.getByRole("button", { name: "Force probe" });
    expect(button).toBeDisabled();

    await user.click(button);

    expect(onProbe).not.toHaveBeenCalled();
  });

  it("shows reset action when reset credits are available", async () => {
    const user = userEvent.setup();
    const onResetCredit = vi.fn();
    const account = createAccountSummary({
      availableResetCredits: 3,
      resetCreditNearestExpiresAt: "2026-01-03T12:00:00.000Z",
    });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={vi.fn()}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={onResetCredit}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Reset (3)" }));

    expect(onResetCredit).toHaveBeenCalledWith(account.accountId);
  });

  it("hides the reset action expiry label when disabled by settings", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T12:00:00.000Z"));
    try {
      const account = createAccountSummary({
        availableResetCredits: 3,
        resetCreditNearestExpiresAt: "2026-01-01T14:00:00.000Z",
      });

      render(
        <AccountActions
          account={account}
          busy={false}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onProbe={vi.fn()}
          onWarmup={vi.fn()}
          onDelete={vi.fn()}
          onReauth={vi.fn()}
          onExportAuth={vi.fn()}
          onResetCredit={vi.fn()}
          showResetCreditExpiryBadge={false}
          onSecurityWorkAuthorizedChange={vi.fn()}
          onLimitWarmupChange={vi.fn()}
          onRoutingPolicyChange={vi.fn()}
        />,
      );

      expect(screen.getByRole("button", { name: "Reset (3)" })).toBeInTheDocument();
      expect(screen.queryByText("2h")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it.each(["paused", "deactivated", "reauth_required"] as const)(
    "disables reset action for %s accounts",
    async (status) => {
      const user = userEvent.setup();
      const onResetCredit = vi.fn();
      const account = createAccountSummary({
        status,
        availableResetCredits: 2,
        resetCreditNearestExpiresAt: "2026-01-03T12:00:00.000Z",
      });

      render(
        <AccountActions
          account={account}
          busy={false}
          onPause={vi.fn()}
          onResume={vi.fn()}
          onProbe={vi.fn()}
          onWarmup={vi.fn()}
          onDelete={vi.fn()}
          onReauth={vi.fn()}
          onExportAuth={vi.fn()}
          onResetCredit={onResetCredit}
          onSecurityWorkAuthorizedChange={vi.fn()}
          onLimitWarmupChange={vi.fn()}
          onRoutingPolicyChange={vi.fn()}
        />,
      );

      const button = screen.getByRole("button", { name: "Reset (2)" });
      expect(button).toBeDisabled();
      await user.click(button);
      expect(onResetCredit).not.toHaveBeenCalled();
    },
  );

  it("hides reset action when no reset credits are available", () => {
    const account = createAccountSummary({
      availableResetCredits: 0,
      resetCreditNearestExpiresAt: null,
    });

    render(
      <AccountActions
        account={account}
        busy={false}
        onPause={vi.fn()}
        onResume={vi.fn()}
        onProbe={vi.fn()}
        onWarmup={vi.fn()}
        onDelete={vi.fn()}
        onReauth={vi.fn()}
        onExportAuth={vi.fn()}
        onResetCredit={vi.fn()}
        onSecurityWorkAuthorizedChange={vi.fn()}
        onLimitWarmupChange={vi.fn()}
        onRoutingPolicyChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /Reset \(/ })).not.toBeInTheDocument();
  });
});
