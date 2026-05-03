import type { FC } from 'react';
import { useDashboardData, type IndicatorSlot } from '@/hooks/useDashboardData';
import { IndicatorCardView, type BadgeInfo } from '@/components/IndicatorCardView';
import { registerCard } from './registry';

type Extra = Record<string, unknown>;

interface IndicatorConfig {
  key: string;
  label: string;
  formatValue: (v: number, extra: Extra) => string;
  formatSub:   (extra: Extra, ts: string) => string;
  formatBadge?: (extra: Extra, value: number) => BadgeInfo | null;
  valueClass?: (v: number, extra: Extra) => string | undefined;
}

function fmtDate(iso: string): string {
  return iso ? iso.slice(0, 10) : '';
}

function asNumber(v: unknown): number | null {
  return typeof v === 'number' ? v : null;
}

function asString(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function changePctBadge(extra: Extra): BadgeInfo | null {
  const pct = asNumber(extra.change_pct);
  if (pct == null) return null;
  const tone: BadgeInfo['tone'] = pct >= 0 ? 'up' : 'down';
  const text = (pct >= 0 ? '▲ +' : '▼ ') + Math.abs(pct).toFixed(2) + '%';
  return { text, tone };
}

const SIGNED_OKU = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(2) + ' 億';
const SIGNED_CLASS = (v: number) => (v >= 0 ? 'text-green-600' : 'text-red-600');
const UPDATED_SUB = (_e: Extra, ts: string) => `更新 ${fmtDate(ts)}`;

const CONFIGS: IndicatorConfig[] = [
  {
    key: 'taiex',
    label: '加權指數',
    formatValue: (v) => v.toLocaleString(),
    formatSub: (extra, ts) => {
      const prev = asNumber(extra.prev_close);
      return `前收 ${prev != null ? prev.toLocaleString() : '—'} · 更新 ${fmtDate(ts)}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'fx',
    label: '台幣兌美金',
    formatValue: (v) => v.toFixed(2),
    formatSub: (extra, ts) => {
      const prev = asNumber(extra.prev_close);
      return `前收 ${prev != null ? prev.toFixed(2) : '—'} · 更新 ${fmtDate(ts)}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'tw_volume',
    label: '台股成交金額',
    formatValue: (v) => v.toLocaleString() + ' 億',
    formatSub: (extra, ts) => {
      const prev = asNumber(extra.prev_value);
      return `前日 ${prev != null ? prev.toLocaleString() : '—'} 億 · 更新 ${fmtDate(ts)}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'us_volume',
    label: '美股 S&P500 成交量',
    formatValue: (v) => v.toLocaleString() + ' 億股',
    formatSub: (extra, ts) => {
      const prev = asNumber(extra.prev_value);
      return `前日 ${prev != null ? prev.toLocaleString() : '—'} 億股 · 更新 ${fmtDate(ts)}`;
    },
    formatBadge: (extra) => changePctBadge(extra),
  },
  {
    key: 'fear_greed',
    label: '恐懼貪婪指數',
    formatValue: (v) => String(v),
    formatSub: UPDATED_SUB,
    formatBadge: (extra) => {
      const label = asString(extra.label);
      return label ? { text: label, tone: 'neutral' } : null;
    },
    valueClass: (v) => (v < 45 ? 'text-red-600' : v > 55 ? 'text-green-600' : undefined),
  },
  {
    key: 'ndc',
    label: '國發會景氣指標',
    formatValue: (v) => `${v} 分`,
    formatSub: (extra) => `${asString(extra.period)} · 每月更新`,
    formatBadge: (extra) => {
      const light = asString(extra.light);
      return light ? { text: light, tone: 'neutral' } : null;
    },
  },
  {
    key: 'margin_balance',
    label: '融資餘額',
    formatValue: (v) => v.toFixed(0) + ' 億',
    formatSub: UPDATED_SUB,
  },
  {
    key: 'short_balance',
    label: '融券餘額',
    formatValue: (v) => (v / 1000).toFixed(0) + ' 千張',
    formatSub: UPDATED_SUB,
  },
  {
    key: 'short_margin_ratio',
    label: '券資比',
    formatValue: (v) => v.toFixed(2) + ' %',
    formatSub: UPDATED_SUB,
  },
  {
    key: 'total_foreign_net',
    label: '外資淨買超',
    formatValue: SIGNED_OKU,
    formatSub: UPDATED_SUB,
    valueClass: SIGNED_CLASS,
  },
  {
    key: 'total_trust_net',
    label: '投信淨買超',
    formatValue: SIGNED_OKU,
    formatSub: UPDATED_SUB,
    valueClass: SIGNED_CLASS,
  },
  {
    key: 'total_dealer_net',
    label: '自營商淨買超',
    formatValue: SIGNED_OKU,
    formatSub: UPDATED_SUB,
    valueClass: SIGNED_CLASS,
  },
];

function makeCard(cfg: IndicatorConfig): FC {
  return function IndicatorCard() {
    const { data, isLoading, isError } = useDashboardData();
    const slot: IndicatorSlot | undefined = data?.[cfg.key];
    const error = isError
      ? '無法載入'
      : data && !slot
        ? '尚無資料'
        : undefined;
    return (
      <IndicatorCardView
        title={cfg.label}
        loading={isLoading}
        error={error}
        value={slot ? cfg.formatValue(slot.value, slot.extra) : undefined}
        valueClass={slot ? cfg.valueClass?.(slot.value, slot.extra) : undefined}
        sub={slot ? cfg.formatSub(slot.extra, slot.timestamp) : undefined}
        badge={slot ? cfg.formatBadge?.(slot.extra, slot.value) ?? null : null}
      />
    );
  };
}

CONFIGS.forEach((cfg) =>
  registerCard({
    id: cfg.key,
    label: cfg.label,
    defaultPage: 'dashboard',
    component: makeCard(cfg),
  }),
);
