import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api-client';

export interface WatchlistRow {
  ticker: string;
  name: string;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string | null;
  timestamp: string | null;
}

export function useWatchlist() {
  return useQuery<WatchlistRow[]>({
    queryKey: ['stocks'],
    queryFn: () => apiFetch<WatchlistRow[]>('/api/stocks'),
  });
}
