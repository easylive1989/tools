import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from './setup';
import { AlertCreateDialog } from '../src/components/AlertCreateDialog';
import { Button } from '../src/components/ui/button';

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AlertCreateDialog trigger={<Button>open</Button>} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  server.use(
    http.get('*/api/stocks', () =>
      HttpResponse.json([
        {
          ticker: '2330.TW', name: '台積電',
          price: null, change: null, change_pct: null, currency: null, timestamp: null,
        },
      ]),
    ),
  );
});

describe('AlertCreateDialog cascade', () => {
  it('default target_type=indicator hides indicator_key', async () => {
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    await waitFor(() => expect(screen.getByText('類型')).toBeInTheDocument());
    expect(screen.queryByText('個股指標', { selector: 'label' })).not.toBeInTheDocument();
  });

  it('switching to 個股指標 reveals indicator_key; target options come from watchlist', async () => {
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    const typeTrigger = screen.getAllByRole('combobox')[0];
    await userEvent.click(typeTrigger);
    await userEvent.click(screen.getByRole('option', { name: '個股指標' }));

    await waitFor(() =>
      expect(screen.getByText('個股指標', { selector: 'label' })).toBeInTheDocument(),
    );

    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    expect(await screen.findByRole('option', { name: '2330.TW · 台積電' })).toBeInTheDocument();
  });
});
