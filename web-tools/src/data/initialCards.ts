export interface TravelCard {
  id: string;
  chinese: string;
  english: string;
  category: string;
  isCustom?: boolean;
}

export const initialCards: TravelCard[] = [
  // 機場/海關
  { id: "1", chinese: "我的護照在那裡。", english: "My passport is over there.", category: "機場/海關" },
  { id: "2", chinese: "我要辦理登機手續。", english: "I would like to check in.", category: "機場/海關" },
  { id: "3", chinese: "這是我的行李。", english: "This is my luggage.", category: "機場/海關" },
  { id: "4", chinese: "我是來旅遊的。", english: "I am here for sightseeing.", category: "機場/海關" },
  
  // 交通/問路
  { id: "5", chinese: "請問地鐵站在哪裡？", english: "Where is the subway station?", category: "交通/問路" },
  { id: "6", chinese: "我想去這個地方。", english: "I want to go to this place.", category: "交通/問路" },
  { id: "7", chinese: "這班車去市中心嗎？", english: "Does this bus go to the city center?", category: "交通/問路" },
  { id: "8", chinese: "請帶我去這個地址。", english: "Please take me to this address.", category: "交通/問路" },

  // 餐廳點餐
  { id: "9", chinese: "我想預約兩人的位子。", english: "I would like to make a reservation for two.", category: "餐廳點餐" },
  { id: "10", chinese: "有菜單嗎？", english: "May I have the menu?", category: "餐廳點餐" },
  { id: "11", chinese: "我想點這個。", english: "I would like to order this.", category: "餐廳點餐" },
  { id: "12", chinese: "買單，謝謝。", english: "Check, please. Thank you.", category: "餐廳點餐" },

  // 購物/退稅
  { id: "13", chinese: "這個多少錢？", english: "How much is this?", category: "購物/退稅" },
  { id: "14", chinese: "有更便宜的嗎？", english: "Is there anything cheaper?", category: "購物/退稅" },
  { id: "15", chinese: "可以刷卡嗎？", english: "Can I pay by credit card?", category: "購物/退稅" },
  { id: "16", chinese: "我想要辦理退稅。", english: "I would like to get a tax refund.", category: "購物/退稅" },
];

export const categories = ["全部", "機場/海關", "交通/問路", "餐廳點餐", "購物/退稅", "自定義"];
