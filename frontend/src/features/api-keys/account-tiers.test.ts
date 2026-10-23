import { describe, expect, it } from "vitest";

import {
  accountTiersEqual,
  addAccountToTiers,
  moveAccountInTiers,
  removeAccountFromTiers,
  sharesRankWithAbove,
  tiersFromAccountIds,
  toggleShareRankWithAbove,
} from "@/features/api-keys/account-tiers";

describe("account tiers", () => {
  it("treats a flat list as one account per rank", () => {
    expect(tiersFromAccountIds(["a", "b"])).toEqual([["a"], ["b"]]);
  });

  it("appends a new account as the lowest rank and ignores duplicates", () => {
    expect(addAccountToTiers([["a", "b"]], "c")).toEqual([["a", "b"], ["c"]]);
    expect(addAccountToTiers([["a", "b"]], "b")).toEqual([["a", "b"]]);
  });

  it("removes an account without merging the tiers around it", () => {
    expect(removeAccountFromTiers([["a"], ["b"], ["c", "d"]], "b")).toEqual([["a"], ["c", "d"]]);
    expect(removeAccountFromTiers([["a", "b"], ["c"]], "a")).toEqual([["b"], ["c"]]);
  });

  it("joins an account into the rank above and splits it off again", () => {
    const joined = toggleShareRankWithAbove([["a"], ["b"], ["c"]], 1);
    expect(joined).toEqual([["a", "b"], ["c"]]);
    expect(sharesRankWithAbove(joined, 1)).toBe(true);
    expect(sharesRankWithAbove(joined, 2)).toBe(false);
    expect(toggleShareRankWithAbove(joined, 1)).toEqual([["a"], ["b"], ["c"]]);
  });

  it("never lets the first account share a rank", () => {
    expect(toggleShareRankWithAbove([["a"], ["b"]], 0)).toEqual([["a"], ["b"]]);
    expect(sharesRankWithAbove([["a"], ["b"]], 0)).toBe(false);
  });

  it("moves accounts by position, so crossing a boundary changes rank", () => {
    // [a b] [c]: moving c up swaps it with b, which drops to rank 2.
    expect(moveAccountInTiers([["a", "b"], ["c"]], 2, -1)).toEqual([["a", "c"], ["b"]]);
    expect(moveAccountInTiers([["a"], ["b"]], 0, -1)).toEqual([["a"], ["b"]]);
  });

  it("compares tiers ignoring order inside a tier", () => {
    expect(accountTiersEqual([["a", "b"], ["c"]], [["b", "a"], ["c"]])).toBe(true);
    expect(accountTiersEqual([["a", "b"], ["c"]], [["a"], ["b"], ["c"]])).toBe(false);
    expect(accountTiersEqual([["a"], ["b"]], [["b"], ["a"]])).toBe(false);
  });
});
