import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/dashboard-cards';
import { listCards } from '../src/cards/registry';

function renderCard(id: string) {
  const spec = listCards('dashboard').find((c) => c.id === id);
  if (!spec) throw new Error(`card ${id} not registered`);
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Card />
    </QueryClientProvider>,
  );
}

describe('dashboard-cards', () => {
  it('registers 12 cards on the dashboard page', () => {
    expect(listCards('dashboard').length).toBe(12);
  });

  it('taiex renders main value + change_pct badge + prev_close in sub', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          taiex: {
            value: 18234.56,
            timestamp: '2026-05-02T08:00:00Z',
            extra: { change_pct: 1.23, prev_close: 18011 },
          },
        }),
      ),
    );
    renderCard('taiex');
    await waitFor(() => {
      expect(screen.getByText('18,234.56')).toBeInTheDocument();
      expect(screen.getByText('▲ +1.23%')).toBeInTheDocument();
      expect(screen.getByText(/前收 18,011/)).toBeInTheDocument();
    });
  });

  it('total_foreign_net colors red when negative', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          total_foreign_net: { value: -5.5, timestamp: '2026-05-02T00:00:00Z', extra: {} },
        }),
      ),
    );
    renderCard('total_foreign_net');
    await waitFor(() => {
      expect(screen.getByText('-5.50 億')).toHaveClass('text-red-600');
    });
  });

  it('ndc shows period in sub line and light as badge', async () => {
    server.use(
      http.get('*/api/dashboard', () =>
        HttpResponse.json({
          ndc: { value: 28, timestamp: '2026-05-02T00:00:00Z', extra: { period: '2026-04', light: '綠燈' } },
        }),
      ),
    );
    renderCard('ndc');
    await waitFor(() => {
      expect(screen.getByText('28 分')).toBeInTheDocument();
      expect(screen.getByText(/2026-04 · 每月更新/)).toBeInTheDocument();
      expect(screen.getByText('綠燈')).toBeInTheDocument();
    });
  });
});
