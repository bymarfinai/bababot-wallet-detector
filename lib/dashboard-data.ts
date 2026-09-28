import type {
  DashboardPayload,
  DashboardSymbol,
  WindowKey,
} from "./dashboard-types";

const nowSeconds = () => Math.floor(Date.now() / 1000);

const symbols: DashboardSymbol[] = [
  {
    symbol: "WIF",
    baseAsset: "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzL56aC3B8Dg9t",
    flowState: "ACCUMULATION",
    eventCount: 9,
    buyEventCount: 8,
    sellEventCount: 1,
    uniqueWalletCount: 7,
    buyWalletCount: 7,
    sellWalletCount: 1,
    netBaseAmount: "28450",
    usdBuyNotional: "47260",
    usdSellNotional: "6310",
    usdNetNotional: "40950",
    unpricedEventCount: 1,
    lastActivityTime: nowSeconds() - 42,
    segmentMembership: {
      S1: { buyWalletCount: 4, sellWalletCount: 0 },
      S2: { buyWalletCount: 3, sellWalletCount: 1 },
      S3: { buyWalletCount: 1, sellWalletCount: 0 },
    },
  },
  {
    symbol: "BONK",
    baseAsset: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6N4e8Q7D6g2fS4bN",
    flowState: "ACCUMULATION",
    eventCount: 5,
    buyEventCount: 5,
    sellEventCount: 0,
    uniqueWalletCount: 5,
    buyWalletCount: 5,
    sellWalletCount: 0,
    netBaseAmount: "483100000",
    usdBuyNotional: "18420",
    usdSellNotional: "0",
    usdNetNotional: "18420",
    unpricedEventCount: 0,
    lastActivityTime: nowSeconds() - 126,
    segmentMembership: {
      S1: { buyWalletCount: 2, sellWalletCount: 0 },
      S2: { buyWalletCount: 2, sellWalletCount: 0 },
      S3: { buyWalletCount: 2, sellWalletCount: 0 },
    },
  },
  {
    symbol: "JUP",
    baseAsset: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    flowState: "DISTRIBUTION",
    eventCount: 8,
    buyEventCount: 2,
    sellEventCount: 6,
    uniqueWalletCount: 6,
    buyWalletCount: 2,
    sellWalletCount: 5,
    netBaseAmount: "-9150",
    usdBuyNotional: "9210",
    usdSellNotional: "27860",
    usdNetNotional: "-18650",
    unpricedEventCount: 0,
    lastActivityTime: nowSeconds() - 218,
    segmentMembership: {
      S1: { buyWalletCount: 1, sellWalletCount: 3 },
      S2: { buyWalletCount: 1, sellWalletCount: 2 },
      S3: { buyWalletCount: 0, sellWalletCount: 1 },
    },
  },
];

function windowOf(
  key: WindowKey,
  multiplier: number,
): DashboardPayload["windows"][WindowKey] {
  const seconds = key === "5m" ? 300 : key === "15m" ? 900 : 3600;
  return {
    windowSeconds: seconds,
    tradeEventCount: symbols.reduce((total, row) => total + row.eventCount, 0) * multiplier,
    symbolCount: symbols.length,
    symbols: symbols.map((row) => ({
      ...row,
      eventCount: row.eventCount * multiplier,
      buyEventCount: row.buyEventCount * multiplier,
      sellEventCount: row.sellEventCount * multiplier,
    })),
  };
}

export function demoDashboardPayload(): DashboardPayload {
  const now = nowSeconds();
  return {
    mode: "DEMO",
    generatedAt: new Date().toISOString(),
    sourceMessage:
      "Stage 8 runtime is not deployed yet. This view uses contract-safe demo data and never presents it as live.",
    registry: {
      snapshotId: "demo-stage8-snapshot",
      activeWalletCount: 284,
      statusCounts: { ACTIVE: 284, UNQUALIFIED: 91, NOT_READY: 37 },
      segmentCounts: { S1: 173, S2: 104, S3: 39 },
    },
    monitor: {
      activeWalletCount: 284,
      ingestAttempts: 1284,
      storedEventCount: 1168,
      storedTradeEventCount: 986,
      duplicateWalletEventCount: 93,
      normalizationErrorCount: 3,
      latestBlockTime: now - 42,
    },
    windows: {
      "5m": windowOf("5m", 1),
      "15m": windowOf("15m", 2),
      "1h": windowOf("1h", 5),
    },
    recentEvents: [
      {
        id: "demo-1",
        blockTime: now - 42,
        wallet: "86xCnPeV69n6t3DnyGvkKobf9FdN2H9oiVDdaMpo2MMY",
        side: "BUY",
        symbol: "WIF",
        baseAsset: symbols[0].baseAsset,
        usdNotional: "14200",
        primarySegment: "S1",
        qualifyingSegments: ["S1", "S2"],
      },
      {
        id: "demo-2",
        blockTime: now - 86,
        wallet: "22222222222222222222222222222222",
        side: "BUY",
        symbol: "BONK",
        baseAsset: symbols[1].baseAsset,
        usdNotional: "8400",
        primarySegment: "S2",
        qualifyingSegments: ["S2"],
      },
      {
        id: "demo-3",
        blockTime: now - 134,
        wallet: "33333333333333333333333333333333",
        side: "SELL",
        symbol: "JUP",
        baseAsset: symbols[2].baseAsset,
        usdNotional: "7310",
        primarySegment: "S1",
        qualifyingSegments: ["S1"],
      },
      {
        id: "demo-4",
        blockTime: now - 202,
        wallet: "44444444444444444444444444444444",
        side: "BUY",
        symbol: "WIF",
        baseAsset: symbols[0].baseAsset,
        usdNotional: null,
        primarySegment: "S3",
        qualifyingSegments: ["S2", "S3"],
      },
    ],
  };
}

function isDashboardPayload(value: unknown): value is DashboardPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<DashboardPayload>;
  return Boolean(
    payload.registry &&
      payload.monitor &&
      payload.windows &&
      payload.recentEvents &&
      payload.generatedAt,
  );
}

export async function getDashboardPayload(): Promise<DashboardPayload> {
  const endpoint = process.env.WALLET_DETECTOR_DASHBOARD_URL;

  if (!endpoint) {
    return demoDashboardPayload();
  }

  try {
    const response = await fetch(endpoint, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(process.env.WALLET_DETECTOR_DASHBOARD_TOKEN
          ? {
              Authorization: `Bearer ${process.env.WALLET_DETECTOR_DASHBOARD_TOKEN}`,
            }
          : {}),
      },
    });

    if (!response.ok) {
      throw new Error(`dashboard backend returned ${response.status}`);
    }

    const payload: unknown = await response.json();
    if (!isDashboardPayload(payload)) {
      throw new Error("dashboard backend returned an incompatible payload");
    }

    return {
      ...payload,
      mode: "LIVE",
      sourceMessage: "Connected to Stage 8 runtime backend.",
    };
  } catch (error) {
    const fallback = demoDashboardPayload();
    return {
      ...fallback,
      mode: "OFFLINE",
      sourceMessage:
        error instanceof Error
          ? `Live backend unavailable: ${error.message}. Showing contract-safe demo data.`
          : "Live backend unavailable. Showing contract-safe demo data.",
    };
  }
}
