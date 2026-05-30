import { describe, expect, it } from "vitest";
import { chunkParagraphs } from "../src/chunk";

describe("chunkParagraphs", () => {
  it("空輸入回傳空陣列", () => {
    expect(chunkParagraphs([], 100)).toEqual([]);
  });

  it("全部塞得下時只回一批", () => {
    const out = chunkParagraphs(["aaa", "bbb"], 100);
    expect(out).toEqual(["aaa\n\nbbb"]);
  });

  it("超過上限時切成多批(以 \\n\\n 連接計長)", () => {
    // "aaaa"(4) + "\n\n"(2) + "bbbb"(4) = 10 > 8,所以拆開
    const out = chunkParagraphs(["aaaa", "bbbb"], 8);
    expect(out).toEqual(["aaaa", "bbbb"]);
  });

  it("單一段落超過上限時自成一批,不硬切字", () => {
    const long = "x".repeat(50);
    const out = chunkParagraphs([long, "y"], 10);
    expect(out).toEqual([long, "y"]);
  });
});
