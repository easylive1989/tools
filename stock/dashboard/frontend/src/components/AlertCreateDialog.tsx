import { useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { useWatchlist } from '@/hooks/useWatchlist';
import { INDICATOR_LABELS, STOCK_INDICATOR_LABELS } from '@/lib/alert-labels';

type TargetType = 'indicator' | 'stock' | 'stock_indicator';

interface Props {
  trigger: React.ReactNode;
}

export function AlertCreateDialog({ trigger }: Props) {
  const [open, setOpen] = useState(false);
  const [targetType, setTargetType] = useState<TargetType>('indicator');
  const [target, setTarget] = useState('');
  const [indicatorKey, setIndicatorKey] = useState('per');
  const watchlist = useWatchlist();

  const indicatorOptions = Object.entries(INDICATOR_LABELS);
  const stockIndicatorOptions = Object.entries(STOCK_INDICATOR_LABELS);
  const tickerOptions = watchlist.data ?? [];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增價格警示</DialogTitle>
          <DialogDescription>達到門檻時將推送 Discord 通知。</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-sm font-medium block mb-1">類型</label>
            <Select
              value={targetType}
              onValueChange={(v) => {
                setTargetType(v as TargetType);
                setTarget('');
              }}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="indicator">指標</SelectItem>
                <SelectItem value="stock">股票 / ETF</SelectItem>
                <SelectItem value="stock_indicator">個股指標</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">目標</label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger><SelectValue placeholder="選擇" /></SelectTrigger>
              <SelectContent>
                {targetType === 'indicator' && indicatorOptions.map(([k, label]) => (
                  <SelectItem key={k} value={k}>{label}</SelectItem>
                ))}
                {targetType !== 'indicator' && tickerOptions.length === 0 && (
                  <SelectItem value="__none__" disabled>（請先在自選股新增）</SelectItem>
                )}
                {targetType !== 'indicator' && tickerOptions.map((s) => (
                  <SelectItem key={s.ticker} value={s.ticker}>
                    {s.name ? `${s.ticker} · ${s.name}` : s.ticker}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {targetType === 'stock_indicator' && (
            <div>
              <label className="text-sm font-medium block mb-1">個股指標</label>
              <Select value={indicatorKey} onValueChange={setIndicatorKey}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {stockIndicatorOptions.map(([k, label]) => (
                    <SelectItem key={k} value={k}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button disabled>建立</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
