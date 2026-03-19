import { TravelCard } from "@/data/initialCards";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Volume2, Trash2 } from "lucide-react";
import { useTTS } from "@/hooks/useTTS";

interface CardListProps {
  cards: TravelCard[];
  onDelete?: (id: string) => void;
}

export function CardList({ cards, onDelete }: CardListProps) {
  const { speak } = useTTS();

  if (cards.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        沒有找到相關字卡
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map((card) => (
        <Card key={card.id} className="group hover:border-primary transition-colors">
          <CardContent className="p-6 flex flex-col justify-between h-full space-y-4">
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wider">
                {card.category}
              </div>
              <h3 className="text-lg font-bold text-foreground mb-2">
                {card.chinese}
              </h3>
              <p className="text-base text-muted-foreground italic">
                {card.english}
              </p>
            </div>
            
            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => speak(card.english)}
              >
                <Volume2 className="h-4 w-4" /> 播放
              </Button>
              
              {card.isCustom && onDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => onDelete(card.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
