import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApiKeyCacheUsage } from "./api-key-cache-usage";

describe("ApiKeyCacheUsage", () => {
  it("renders per-key input, cached input, and cache-hit ratio labels", () => {
    render(
      <ApiKeyCacheUsage
        data={[
          {
            apiKeyId: "key_reports",
            apiKeyName: "Reports key",
            keyPrefix: "sk-reports",
            requests: 2,
            totalInputTokens: 1000,
            cachedInputTokens: 250,
            cacheHitRatio: 0.25,
          },
        ]}
      />,
    );

    expect(screen.getByText("Cache usage by API key")).toBeInTheDocument();
    expect(screen.getByText("Reports key (sk-reports...)")).toBeInTheDocument();
    expect(screen.getByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("250")).toBeInTheDocument();
    expect(screen.getByText("25.0%")).toBeInTheDocument();
    expect(screen.getByText(/no saved tokens are inferred/i)).toBeInTheDocument();
  });
});
