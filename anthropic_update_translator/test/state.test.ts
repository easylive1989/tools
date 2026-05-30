import { describe, it, expect } from "vitest";
import { State } from "../src/state";
import { MemoryKV, asKV } from "./helpers";

describe("State", () => {
  it("getLastMessageId 預設回 null", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.getLastMessageId()).toBeNull();
  });

  it("setLastMessageId 後可讀回", async () => {
    const state = new State(asKV(new MemoryKV()));
    await state.setLastMessageId("123");
    expect(await state.getLastMessageId()).toBe("123");
  });

  it("getRetryCount 預設回 0", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.getRetryCount("abc")).toBe(0);
  });

  it("incrementRetryCount 回傳新的次數並寫入", async () => {
    const state = new State(asKV(new MemoryKV()));
    expect(await state.incrementRetryCount("abc")).toBe(1);
    expect(await state.incrementRetryCount("abc")).toBe(2);
    expect(await state.getRetryCount("abc")).toBe(2);
  });

  it("clearRetryCount 把 key 移除", async () => {
    const state = new State(asKV(new MemoryKV()));
    await state.incrementRetryCount("abc");
    await state.clearRetryCount("abc");
    expect(await state.getRetryCount("abc")).toBe(0);
  });

  it("getHackMdLink 預設為 null,set 後可取回", async () => {
    const kv = new MemoryKV();
    const state = new State(asKV(kv));
    expect(await state.getHackMdLink("101")).toBeNull();
    await state.setHackMdLink("101", "https://hackmd.io/@x/abc");
    expect(await state.getHackMdLink("101")).toBe("https://hackmd.io/@x/abc");
  });
});
