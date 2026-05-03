import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface BadgeInfo {
  text: string;
  tone: 'up' | 'down' | 'neutral';
}

interface Props {
  title: string;
  value?: string;
  sub?: string;
  badge?: BadgeInfo | null;
  valueClass?: string;
  loading?: boolean;
  error?: string;
}

const TONE_CLASS: Record<BadgeInfo['tone'], string> = {
  up:      'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200',
  down:    'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200',
  neutral: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200',
};

export function IndicatorCardView({
  title, value, sub, badge, valueClass, loading, error,
}: Props) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {badge && (
          <span className={cn('rounded px-2 py-0.5 text-xs', TONE_CLASS[badge.tone])}>
            {badge.text}
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-1">
        {loading && <p className="text-sm text-muted-foreground">載入中…</p>}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!loading && !error && value !== undefined && (
          <p className={cn('text-2xl font-bold', valueClass)}>{value}</p>
        )}
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}
