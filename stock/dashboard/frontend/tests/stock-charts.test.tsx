import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/stock-charts';
import { listCards } from '../src/cards/registry';

function makeHistory(rows: number) {
  const dates: string[] = [];
  const candles: any[] = [];
  for (let i = 0; i < rows; i++) {
    const d = new Date(2026, 4, 1 + i).toISOString().slice(0, 10);
    dates.push(d);
    candles.push({
      open: 100 + i, high: 110 + i, low: 90 + i, close: 105 + i, volume: 1000 + i,
    });
  }
  return {
    ticker: '2330.TW', name: '台積電', currency: 'TWD', time_range: '3M',
    dates, candles,
    indicators: {
      ma5: dates.map((_, i) => 100 + i * 0.5),
      ma20: dates.map((_, i) => 100 + i * 0.3),
      ma60: dates.map((_, i) => 100 + i * 0.1),
      rsi14: dates.map((_, i) => 40 + i * 5),
      macd: dates.map((_, i) => i - 2),
      macd_signal: dates.map((_, i) => i * 0.5 - 1),
      macd_histogram: dates.map((_, i) => (i % 2 === 0 ? 1 : -1)),
    },
  };
}

function renderCardOnPage(id: string) {
  const Card = listCards('stock').find((c) => c.id === id)!.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/stock/2330.TW']}>
        <Routes>
          <Route path="/stock/:code" element={<Card />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('KLineCard', () => {
  it('registers cols=3 on stock page', () => {
    expect(listCards('stock').find((c) => c.id === 'stock-kline')?.cols).toBe(3);
  });

  it('renders the K-line card title', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(4))),
    );
    renderCardOnPage('stock-kline');
    await waitFor(() => expect(screen.getByText('日 K 棒')).toBeInTheDocument());
  });
});

describe('PriceMACard', () => {
  it('registers cols=3 on stock page', () => {
    expect(listCards('stock').find((c) => c.id === 'stock-price-ma')?.cols).toBe(3);
  });

  it('renders the price + MA card title', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(8))),
    );
    renderCardOnPage('stock-price-ma');
    await waitFor(() => expect(screen.getByText('收盤價 + 移動平均')).toBeInTheDocument());
  });
});

describe('VolumeCard', () => {
  it('registers cols=3 on stock page', () => {
    expect(listCards('stock').find((c) => c.id === 'stock-volume')?.cols).toBe(3);
  });

  it('renders the volume card title', async () => {
    server.use(
      http.get('*/api/stocks/2330.TW/history', () => HttpResponse.json(makeHistory(5))),
    );
    renderCardOnPage('stock-volume');
    await waitFor(() => expect(screen.getByText('成交量')).toBeInTheDocument());
  });
});
