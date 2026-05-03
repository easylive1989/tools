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

describe('AlertCreateDialog condition filter', () => {
  it('limits condition options to indicator supported_conditions from spec', async () => {
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [
            { key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above', 'below'] },
          ],
          stock_indicator: [],
        }),
      ),
    );
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));

    const condTrigger = screen.getAllByRole('combobox')[2];
    await userEvent.click(condTrigger);
    expect(screen.getByRole('option', { name: '大於等於' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '小於等於' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /連 N 日/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /百分位/ })).not.toBeInTheDocument();
  });

  it('streak condition reveals N 日 input', async () => {
    server.use(
      http.get('*/api/stocks', () => HttpResponse.json([])),
      http.get('*/api/indicators/spec', () =>
        HttpResponse.json({
          indicator: [
            { key: 'taiex', label: '加權指數', unit: null, supported_conditions: ['above', 'streak_above'] },
          ],
          stock_indicator: [],
        }),
      ),
    );
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    const targetTrigger = screen.getAllByRole('combobox')[1];
    await userEvent.click(targetTrigger);
    await userEvent.click(screen.getByRole('option', { name: '加權指數' }));

    const condTrigger = screen.getAllByRole('combobox')[2];
    await userEvent.click(condTrigger);
    await userEvent.click(screen.getByRole('option', { name: '連 N 日突破' }));

    expect(screen.getByLabelText('N 日')).toBeInTheDocument();
  });
});
