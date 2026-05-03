import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import '../src/cards/TaiexCard';
import { getCard } from '../src/cards/registry';

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('TaiexCard', () => {
  it('registers itself in the card registry', () => {
    expect(getCard('taiex')).toBeDefined();
    expect(getCard('taiex')?.defaultPage).toBe('dashboard');
  });

  it('renders close + change_pct from API', async () => {
    server.use(
      http.get('*/api/indicators/taiex', () =>
        HttpResponse.json({ date: '2026-05-02', close: 18234.56, change_pct: 1.23 })
      )
    );

    const Card = getCard('taiex')!.component;
    renderWithQuery(<Card />);

    await waitFor(() => {
      expect(screen.getByText('18,234.56')).toBeInTheDocument();
      expect(screen.getByText('+1.23%')).toBeInTheDocument();
      expect(screen.getByText('2026-05-02')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    server.use(
      http.get('*/api/indicators/taiex', () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    const Card = getCard('taiex')!.component;
    renderWithQuery(<Card />);

    await waitFor(() => {
      expect(screen.getByText('無法載入')).toBeInTheDocument();
    });
  });
});
