import { useState, useEffect, useMemo } from "react";
import { initialCards, categories, TravelCard } from "@/data/initialCards";
import { SearchBar } from "@/components/SearchBar";
import { CategoryFilter } from "@/components/CategoryFilter";
import { CardList } from "@/components/CardList";
import { AddCardDialog } from "@/components/AddCardDialog";
import { Globe, Plane } from "lucide-react";

export default function App() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("全部");
  const [customCards, setCustomCards] = useState<TravelCard[]>([]);

  // 從 LocalStorage 載入自定義字卡
  useEffect(() => {
    const saved = localStorage.getItem("travel-cards-custom");
    if (saved) {
      try {
        setCustomCards(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load custom cards", e);
      }
    }
  }, []);

  // 儲存自定義字卡到 LocalStorage
  useEffect(() => {
    localStorage.setItem("travel-cards-custom", JSON.stringify(customCards));
  }, [customCards]);

  const allCards = useMemo(() => {
    return [...initialCards, ...customCards];
  }, [customCards]);

  const filteredCards = useMemo(() => {
    return allCards.filter((card) => {
      const matchesSearch =
        card.chinese.toLowerCase().includes(search.toLowerCase()) ||
        card.english.toLowerCase().includes(search.toLowerCase());
      const matchesCategory = category === "全部" || card.category === category;
      return matchesSearch && matchesCategory;
    });
  }, [allCards, search, category]);

  const handleAddCard = (newCard: Omit<TravelCard, "id">) => {
    const cardWithId: TravelCard = {
      ...newCard,
      id: Date.now().toString(),
    };
    setCustomCards((prev) => [cardWithId, ...prev]);
  };

  const handleDeleteCard = (id: string) => {
    setCustomCards((prev) => prev.filter((c) => c.id !== id));
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-primary p-1.5 rounded-lg">
              <Plane className="h-5 w-5 text-white" />
            </div>
            <h1 className="text-xl font-bold tracking-tight">旅遊工具箱</h1>
          </div>
          <div className="flex items-center gap-4 text-sm font-medium text-muted-foreground">
            <span>旅遊字卡 (中英對照)</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 container mx-auto px-4 py-8 space-y-8">
        <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-white p-6 rounded-xl border shadow-sm">
          <div className="flex flex-col md:flex-row gap-4 w-full md:w-auto flex-1">
            <div className="w-full md:w-72">
              <SearchBar value={search} onChange={setSearch} />
            </div>
            <div className="w-full md:w-48">
              <CategoryFilter value={category} onChange={setCategory} categories={categories} />
            </div>
          </div>
          <div className="w-full md:w-auto">
            <AddCardDialog onAdd={handleAddCard} />
          </div>
        </div>

        <section className="space-y-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Globe className="h-4 w-4" />
            <span className="text-sm font-medium">
              正在查看：{category} (共 {filteredCards.length} 筆)
            </span>
          </div>
          <CardList cards={filteredCards} onDelete={handleDeleteCard} />
        </section>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t py-8 mt-auto">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>© 2026 Web-Tools. 旅遊字卡翻譯工具.</p>
        </div>
      </footer>
    </div>
  );
}
