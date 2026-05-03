import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '@/lib/api-client';

export interface ValuationEntry {
  date: string;
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
}

export interface ValuationLatest {
  per: number | null;
  pbr: number | null;
  dividend_yield: number | null;
  per_percentile: number | null;
  pbr_percentile: number | null;
  dividend_yield_percentile: number | null;
}

export interface ValuationResponse {
  ticker: string;
  years: number;
  ok: boolean;
  latest: ValuationLatest;
  entries: ValuationEntry[];
}

export function useValuation(years = 5) {
  const { code = '' } = useParams<{ code: string }>();
  return useQuery<ValuationResponse>({
    queryKey: ['stock-valuation', code, years],
    queryFn: () =>
      apiFetch<ValuationResponse>(
        `/api/stocks/${encodeURIComponent(code)}/valuation?years=${years}`,
      ),
    enabled: !!code,
  });
}
