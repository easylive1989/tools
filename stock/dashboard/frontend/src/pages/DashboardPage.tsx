import { listCards } from '@/cards/registry';
import { useCardPrefsStore } from '@/store/card-prefs-store';
import { DashboardSettingsDialog } from '@/components/DashboardSettingsDialog';
import { cn } from '@/lib/utils';

export default function DashboardPage() {
  const allCards = listCards('dashboard');
  const hiddenIds = useCardPrefsStore((s) => s.hiddenIds);
  const visible = allCards.filter((c) => !hiddenIds.has(c.id));

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <DashboardSettingsDialog />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map(({ id, component: Card, cols = 1 }) => (
          <div
            key={id}
            className={cn(
              cols === 3 && 'lg:col-span-3',
              cols === 2 && 'lg:col-span-2',
            )}
          >
            <Card />
          </div>
        ))}
      </div>
    </div>
  );
}
