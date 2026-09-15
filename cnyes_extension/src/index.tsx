import { ActionPanel, Action, List, Icon, Color } from "@raycast/api";
import { useFetch } from "@raycast/utils";

interface NewsItem {
  newsId: number;
  title: string;
  publishAt: number;
  categoryName?: string;
}

interface ApiResponse {
  statusCode: number;
  items: {
    data: NewsItem[];
  };
}

export default function Command() {
  const { data, isLoading, revalidate } = useFetch<ApiResponse>(
    "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=30",
    {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        Accept: "application/json",
      },
      keepPreviousData: true,
    }
  );

  const items = data?.items?.data ?? [];

  return (
    <List
      isLoading={isLoading}
      searchBarPlaceholder="搜尋即時新聞標題..."
    >
      {items.map((item) => {
        const date = new Date(item.publishAt * 1000);
        const timeStr = date.toLocaleTimeString("zh-TW", {
          hour: "2-digit",
          minute: "2-digit",
        });

        const url = `https://news.cnyes.com/news/id/${item.newsId}`;

        return (
          <List.Item
            key={item.newsId}
            icon={{ source: Icon.LineChart, tintColor: Color.Red }}
            title={item.title}
            accessories={[
              ...(item.categoryName
                ? [{ tag: { value: item.categoryName, color: Color.SecondaryText } }]
                : []),
              { text: timeStr, icon: Icon.Clock },
            ]}
            actions={
              <ActionPanel>
                <Action.OpenInBrowser url={url} title="在瀏覽器開啟新聞" />
                <Action.CopyToClipboard
                  content={url}
                  title="複製新聞連結"
                  shortcut={{ modifiers: ["cmd"], key: "c" }}
                />
                <Action
                  title="重新整理"
                  icon={Icon.RotateAntiClockwise}
                  onAction={revalidate}
                  shortcut={{ modifiers: ["cmd"], key: "r" }}
                />
              </ActionPanel>
            }
          />
        );
      })}
    </List>
  );
}
