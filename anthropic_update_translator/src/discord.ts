import type { DiscordMessage } from "./filter";
import type { OutgoingMessage } from "./format";

const API_BASE = "https://discord.com/api/v10";

export class RateLimitError extends Error {
  name = "RateLimitError";
  constructor(public retryAfterSec: number) {
    super(`Discord rate limited, retry after ${retryAfterSec}s`);
  }
}

export class DiscordClient {
  constructor(private botToken: string) {}

  private headers(): Record<string, string> {
    return {
      Authorization: `Bot ${this.botToken}`,
      "Content-Type": "application/json",
    };
  }

  async fetchMessagesAfter(
    channelId: string,
    afterMessageId: string,
    limit: number,
  ): Promise<DiscordMessage[]> {
    const url = `${API_BASE}/channels/${channelId}/messages?after=${afterMessageId}&limit=${limit}`;
    const res = await fetch(url, { headers: this.headers() });
    if (res.status === 429) {
      const retryAfter = Number.parseInt(res.headers.get("Retry-After") ?? "5", 10);
      throw new RateLimitError(retryAfter);
    }
    if (!res.ok) {
      throw new Error(`Discord fetchMessagesAfter failed: ${res.status} ${await res.text()}`);
    }
    const data = (await res.json()) as DiscordMessage[];
    return sortBySnowflake(data);
  }

  async fetchLatest(channelId: string): Promise<DiscordMessage[]> {
    const url = `${API_BASE}/channels/${channelId}/messages?limit=1`;
    const res = await fetch(url, { headers: this.headers() });
    if (!res.ok) {
      throw new Error(`Discord fetchLatest failed: ${res.status} ${await res.text()}`);
    }
    return (await res.json()) as DiscordMessage[];
  }

  async postMessage(channelId: string, payload: OutgoingMessage): Promise<void> {
    const url = `${API_BASE}/channels/${channelId}/messages`;
    const res = await fetch(url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Discord postMessage failed: ${res.status} ${await res.text()}`);
    }
  }
}

function sortBySnowflake(msgs: DiscordMessage[]): DiscordMessage[] {
  return [...msgs].sort((a, b) => {
    const ai = BigInt(a.id);
    const bi = BigInt(b.id);
    if (ai < bi) return -1;
    if (ai > bi) return 1;
    return 0;
  });
}
