import { afterEach, describe, expect, it, vi } from "vitest";
import { HackMdClient } from "../src/hackmd";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HackMdClient", () => {
  it("POST 到 /v1/notes 帶正確 header 與 body,回傳 publishLink", async () => {
    let capturedUrl = "";
    let capturedInit: RequestInit = {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        capturedUrl = url;
        capturedInit = init;
        return Promise.resolve(
          new Response(JSON.stringify({ id: "abc", publishLink: "https://hackmd.io/@x/abc" }), {
            status: 201,
          }),
        );
      }),
    );

    const client = new HackMdClient("TOKEN");
    const out = await client.createNote("# Title\n\nbody");

    expect(out.publishLink).toBe("https://hackmd.io/@x/abc");
    expect(capturedUrl).toBe("https://api.hackmd.io/v1/notes");
    const headers = capturedInit.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer TOKEN");
    const body = JSON.parse(capturedInit.body as string);
    expect(body.content).toBe("# Title\n\nbody");
    expect(body.readPermission).toBe("guest");
    expect(body.writePermission).toBe("owner");
  });

  it("非 2xx 時丟錯", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("nope", { status: 403 }))));
    const client = new HackMdClient("TOKEN");
    await expect(client.createNote("x")).rejects.toThrow(/HackMD createNote failed/);
  });

  it("回應缺 publishLink 時丟錯", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ id: "abc" }), { status: 201 }))),
    );
    const client = new HackMdClient("TOKEN");
    await expect(client.createNote("x")).rejects.toThrow(/missing publishLink/);
  });
});
