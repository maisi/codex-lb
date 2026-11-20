import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { OracleStorageNotice } from "@/features/dashboard/components/oracle-storage-notice";
import { signInAsTeamAdmin } from "@/test/access-test-utils";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/utils";

const path = "/api/runtime/oracle-storage";
const warning = { level: "warning", freeBytes: 2 * 2 ** 30, maintenance: "idle" };

describe("Oracle storage warning", () => {
  it("queues a manual check and shows the saved status", async () => {
    signInAsTeamAdmin();
    server.use(
      http.get(path, () => HttpResponse.json(warning)),
      http.post(path + "/maintenance", () => HttpResponse.json({ ...warning, maintenance: "queued" })),
    );
    renderWithProviders(<OracleStorageNotice />);
    fireEvent.click(await screen.findByRole("button", { name: "Run maintenance" }));
    expect(await screen.findByText("Maintenance is queued.")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each(["critical", "warning"])("shows %s pressure to viewers without an action", async (level) => {
    signInAsTeamAdmin({ permissions: ["dashboard:read:all"] });
    server.use(http.get(path, () => HttpResponse.json({ ...warning, level })));
    renderWithProviders(<OracleStorageNotice />);
    expect(await screen.findByRole("region", { name: "Oracle storage" })).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows automatic maintenance under 2 GiB without a button for admins", async () => {
    signInAsTeamAdmin();
    server.use(http.get(path, () => HttpResponse.json({ ...warning, level: "critical", freeBytes: 1, maintenance: "running" })));
    renderWithProviders(<OracleStorageNotice />);
    expect(await screen.findByText("Online maintenance is running.")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows when a safe online move cannot fit", async () => {
    signInAsTeamAdmin();
    server.use(http.get(path, () => HttpResponse.json({ ...warning, level: "critical", maintenance: "no_space" })));
    renderWithProviders(<OracleStorageNotice />);
    expect(await screen.findByText(/too little working space/i)).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([null, { ...warning, level: "healthy" }])("hides the notice when no action is needed", async (status) => {
    signInAsTeamAdmin();
    server.use(http.get(path, () => HttpResponse.json(status)));
    const { queryClient } = renderWithProviders(<OracleStorageNotice />);
    await waitFor(() => expect(queryClient.getQueryState(["runtime", "oracle-storage"])?.status).toBe("success"));
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
