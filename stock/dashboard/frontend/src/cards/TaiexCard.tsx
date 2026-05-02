import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiFetch } from '@/lib/api-client';
import { registerCard } from './registry';

interface TaiexResponse {
  date: string;
  close: number;
  change_pct: number;
}

function TaiexCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['taiex'],
    queryFn: () => apiFetch<TaiexResponse>('/api/indicators/taiex'),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>加權指數</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {isError && <p className="text-sm text-destructive">無法載入</p>}
        {data && (
          <div className="space-y-1">
            <p className="text-2xl font-bold">{data.close.toLocaleString()}</p>
            <p
              className={
                data.change_pct >= 0
                  ? 'text-sm text-green-600'
                  : 'text-sm text-red-600'
              }
            >
              {data.change_pct >= 0 ? '+' : ''}
              {data.change_pct.toFixed(2)}%
            </p>
            <p className="text-xs text-muted-foreground">{data.date}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

registerCard({
  id: 'taiex',
  label: '加權指數',
  defaultPage: 'dashboard',
  component: TaiexCard,
});
