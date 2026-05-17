export class MemoryKV {
  store = new Map<string, string>();

  async get(key: string): Promise<string | null> {
    return this.store.get(key) ?? null;
  }

  async put(key: string, value: string): Promise<void> {
    this.store.set(key, value);
  }

  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }

  // 其他 KVNamespace 方法不用,留 stub
  list(): never {
    throw new Error("not implemented");
  }
  getWithMetadata(): never {
    throw new Error("not implemented");
  }
}

export function asKV(kv: MemoryKV): KVNamespace {
  return kv as unknown as KVNamespace;
}
