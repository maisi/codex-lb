/**
 * An API key's account priority as rank tiers: most-preferred tier first, and
 * the accounts inside one tier share a rank (the routing strategy balances
 * between them). Every account appears once.
 */
export type AccountTiers = string[][];

export function tiersFromAccountIds(accountIds: string[]): AccountTiers {
  return accountIds.map((accountId) => [accountId]);
}

export function addAccountToTiers(tiers: AccountTiers, accountId: string): AccountTiers {
  if (tiers.some((tier) => tier.includes(accountId))) {
    return tiers;
  }
  return [...tiers, [accountId]];
}

export function removeAccountFromTiers(tiers: AccountTiers, accountId: string): AccountTiers {
  return tiers.map((tier) => tier.filter((current) => current !== accountId)).filter((tier) => tier.length > 0);
}

/** Positions in the flat order that start a new tier. */
function tierStarts(tiers: AccountTiers): boolean[] {
  return tiers.flatMap((tier) => tier.map((_, index) => index === 0));
}

function buildTiers(accountIds: string[], starts: boolean[]): AccountTiers {
  const tiers: AccountTiers = [];
  accountIds.forEach((accountId, index) => {
    if (index === 0 || starts[index]) {
      tiers.push([]);
    }
    tiers[tiers.length - 1].push(accountId);
  });
  return tiers;
}

/**
 * Swap the account at flat position ``index`` with its neighbour. The tier
 * layout stays by position, so moving across a boundary changes the rank.
 */
export function moveAccountInTiers(tiers: AccountTiers, index: number, delta: number): AccountTiers {
  const accountIds = tiers.flat();
  const target = index + delta;
  if (target < 0 || target >= accountIds.length) {
    return tiers;
  }
  [accountIds[index], accountIds[target]] = [accountIds[target], accountIds[index]];
  return buildTiers(accountIds, tierStarts(tiers));
}

/** Give the account at flat position ``index`` the rank of the one above, or split it off again. */
export function toggleShareRankWithAbove(tiers: AccountTiers, index: number): AccountTiers {
  if (index <= 0) {
    return tiers;
  }
  const starts = tierStarts(tiers);
  starts[index] = !starts[index];
  return buildTiers(tiers.flat(), starts);
}

export function sharesRankWithAbove(tiers: AccountTiers, index: number): boolean {
  return index > 0 && !tierStarts(tiers)[index];
}

/** Same ranks for the same accounts; order inside a tier carries no meaning. */
export function accountTiersEqual(left: AccountTiers, right: AccountTiers): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((tier, index) => {
    const other = right[index];
    if (tier.length !== other.length) {
      return false;
    }
    const otherIds = new Set(other);
    return tier.every((accountId) => otherIds.has(accountId));
  });
}
