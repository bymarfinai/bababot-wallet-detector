export type RuntimeMode = "LIVE" | "DEMO" | "OFFLINE";
export type WindowKey = "5m" | "15m" | "1h";
export type FlowState = "ACCUMULATION" | "DISTRIBUTION" | "BALANCED";

export interface DashboardSymbol {
  symbol: string;
  baseAsset: string;
  flowState: FlowState;
  eventCount: number;
  buyEventCount: number;
  sellEventCount: number;
  uniqueWalletCount: number;
  buyWalletCount: number;
  sellWalletCount: number;
  netBaseAmount: string;
  usdBuyNotional: string;
  usdSellNotional: string;
  usdNetNotional: string;
  unpricedEventCount: number;
  lastActivityTime: number | null;
  segmentMembership: Record<
    string,
    { buyWalletCount: number; sellWalletCount: number }
  >;
}

export interface DashboardWindow {
  windowSeconds: number;
  tradeEventCount: number;
  symbolCount: number;
  symbols: DashboardSymbol[];
}

export interface RecentWalletEvent {
  id: string;
  blockTime: number;
  wallet: string;
  side: "BUY" | "SELL";
  symbol: string;
  baseAsset: string;
  usdNotional: string | null;
  primarySegment: string | null;
  qualifyingSegments: string[];
}

export interface DashboardPayload {
  mode: RuntimeMode;
  generatedAt: string;
  sourceMessage: string;
  registry: {
    snapshotId: string;
    activeWalletCount: number;
    statusCounts: Record<string, number>;
    segmentCounts: Record<string, number>;
  };
  monitor: {
    activeWalletCount: number;
    ingestAttempts: number;
    storedEventCount: number;
    storedTradeEventCount: number;
    duplicateWalletEventCount: number;
    normalizationErrorCount: number;
    latestBlockTime: number | null;
  };
  windows: Record<WindowKey, DashboardWindow>;
  recentEvents: RecentWalletEvent[];
}
