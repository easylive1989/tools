const LAST_MESSAGE_KEY = "last_message_id";
const RETRY_PREFIX = "retry:";
const HACKMD_PREFIX = "hackmd:";

export class State {
  constructor(private kv: KVNamespace) {}

  async getLastMessageId(): Promise<string | null> {
    return this.kv.get(LAST_MESSAGE_KEY);
  }

  async setLastMessageId(id: string): Promise<void> {
    await this.kv.put(LAST_MESSAGE_KEY, id);
  }

  async getRetryCount(messageId: string): Promise<number> {
    const raw = await this.kv.get(RETRY_PREFIX + messageId);
    if (raw === null) return 0;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  }

  async incrementRetryCount(messageId: string): Promise<number> {
    const next = (await this.getRetryCount(messageId)) + 1;
    await this.kv.put(RETRY_PREFIX + messageId, String(next));
    return next;
  }

  async clearRetryCount(messageId: string): Promise<void> {
    await this.kv.delete(RETRY_PREFIX + messageId);
  }

  async getHackMdLink(messageId: string): Promise<string | null> {
    return this.kv.get(HACKMD_PREFIX + messageId);
  }

  async setHackMdLink(messageId: string, link: string): Promise<void> {
    await this.kv.put(HACKMD_PREFIX + messageId, link);
  }
}
