import { useParams } from 'react-router-dom';
import { listCards } from '@/cards/registry';

export default function StockDetailPage() {
  const { code } = useParams<{ code: string }>();
  const cards = listCards('stock');
  return (
    <div className="container mx-auto p-4 space-y-4">
      <h1 className="text-2xl font-bold">{code}</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map(({ id, component: Card }) => (
          <Card key={id} />
        ))}
      </div>
    </div>
  );
}
