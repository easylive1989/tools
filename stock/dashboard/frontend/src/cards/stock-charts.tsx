import { useMemo } from 'react';
import {
  Bar, CartesianGrid, ComposedChart, Customized, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useStockHistory } from '@/hooks/useStockHistory';
import { flattenHistory, type ChartRow } from '@/lib/flatten-history';
import { registerCard } from './registry';

const CHART_HEIGHT = 320;

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

interface CandleLayerProps {
  rows: ChartRow[];
  xAxisMap?: Record<string, { scale: (v: any) => number; bandSize: number }>;
  yAxisMap?: Record<string, { scale: (v: number) => number }>;
}

function CandleLayer({ rows, xAxisMap, yAxisMap }: CandleLayerProps) {
  if (!xAxisMap || !yAxisMap) return null;
  const xKey = Object.keys(xAxisMap)[0];
  const yKey = Object.keys(yAxisMap)[0];
  if (!xKey || !yKey) return null;
  const x = xAxisMap[xKey];
  const y = yAxisMap[yKey];
  const bandSize = x.bandSize || 0;
  const width = Math.max(2, bandSize * 0.6);
  return (
    <g data-testid="candles">
      {rows.map((r) => {
        const cx = x.scale(r.date) + bandSize / 2;
        const yHigh = y.scale(r.high);
        const yLow = y.scale(r.low);
        const yOpen = y.scale(r.open);
        const yClose = y.scale(r.close);
        const up = r.close >= r.open;
        const fill = up ? '#16a34a' : '#dc2626';
        const top = Math.min(yOpen, yClose);
        const h = Math.max(1, Math.abs(yOpen - yClose));
        return (
          <g key={r.date}>
            <line x1={cx} x2={cx} y1={yHigh} y2={yLow} stroke={fill} strokeWidth={1} />
            <rect x={cx - width / 2} y={top} width={width} height={h} fill={fill} />
          </g>
        );
      })}
    </g>
  );
}

function KLineCard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="日 K 棒">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} />
          <Tooltip
            formatter={(v: number) => v?.toLocaleString?.() ?? v}
            labelFormatter={(label) => label as string}
          />
          {/* Hidden bar so recharts allocates the chart area; the candles are drawn via Customized */}
          <Bar dataKey="high" fill="transparent" isAnimationActive={false} />
          <Customized
            component={(props: any) => (
              <CandleLayer
                rows={rows}
                xAxisMap={props.xAxisMap}
                yAxisMap={props.yAxisMap}
              />
            )}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-kline',
  label: '日 K 棒',
  defaultPage: 'stock',
  component: KLineCard,
  cols: 3,
});

function PriceMACard() {
  const { data } = useStockHistory();
  const rows = useMemo(() => (data ? flattenHistory(data) : []), [data]);
  if (!rows.length) return null;
  return (
    <ChartCard title="收盤價 + 移動平均">
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" hide />
          <YAxis domain={['auto', 'auto']} />
          <Tooltip formatter={(v: number) => v?.toLocaleString?.() ?? v} />
          <Legend />
          <Line dataKey="close" stroke="#52525b" dot={false} strokeWidth={2} />
          <Line dataKey="ma5"   stroke="#f97316" dot={false} />
          <Line dataKey="ma20"  stroke="#3b82f6" dot={false} />
          <Line dataKey="ma60"  stroke="#a855f7" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

registerCard({
  id: 'stock-price-ma',
  label: '收盤價 + 移動平均',
  defaultPage: 'stock',
  component: PriceMACard,
  cols: 3,
});
