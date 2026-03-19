import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Plus } from "lucide-react";
import { TravelCard } from "@/data/initialCards";

interface AddCardDialogProps {
  onAdd: (card: Omit<TravelCard, "id">) => void;
}

export function AddCardDialog({ onAdd }: AddCardDialogProps) {
  const [open, setOpen] = useState(false);
  const [chinese, setChinese] = useState("");
  const [english, setEnglish] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (chinese && english) {
      onAdd({ chinese, english, category: "自定義", isCustom: true });
      setChinese("");
      setEnglish("");
      setOpen(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" /> 新增字卡
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新增自定義旅遊字卡</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">中文</label>
            <Input
              value={chinese}
              onChange={(e) => setChinese(e.target.value)}
              placeholder="例如：請給我一杯水"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">英文</label>
            <Input
              value={english}
              onChange={(e) => setEnglish(e.target.value)}
              placeholder="Example: A glass of water, please."
              required
            />
          </div>
          <Button type="submit" className="w-full">
            儲存
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
