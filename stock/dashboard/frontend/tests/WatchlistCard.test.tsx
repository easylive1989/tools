import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/WatchlistCard';
import { listCards } from '../src/cards/registry';

function renderCard() {
  const spec = listCards('dashboard').find((c) => c.id === 'watchlist')!;
  const Card = spec.component;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Card />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WatchlistCard (read-only)', () => {
  it('registers as cols=3 dashboard card', () => {
    expect(listCards('dashboard').find((c) => c.id === 'watchlist')?.cols).toBe(3);
  });

  it('renders rows with ticker as a link to /stock/:code', async () => {
    server.use(
      http.get('*/api/stocks', () =>
        HttpResponse.json([
          {
            ticker: '2330.TW',
            name: '台積電',
            price: 1000,
            change: 5,
            change_pct: 0.5,
            currency: 'TWD',
            timestamp: '2026-05-02',
          },
        ]),
      ),
    );
    renderCard();
    await waitFor(() => {
      const link = screen.getByRole('link', { name: '2330.TW' });
      expect(link).toHaveAttribute('href', '/stock/2330.TW');
      expect(screen.getByText('台積電')).toBeInTheDocument();
    });
  });
});
