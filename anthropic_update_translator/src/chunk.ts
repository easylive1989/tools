/**
 * 把段落貪婪地組成多批,每批(以 "\n\n" 連接後)的長度不超過 maxChars。
 * 單一段落本身超過 maxChars 時自成一批,不硬切字。
 */
export function chunkParagraphs(paragraphs: string[], maxChars: number): string[] {
  const batches: string[] = [];
  let cur: string[] = [];

  for (const p of paragraphs) {
    if (cur.length > 0) {
      const candidate = [...cur, p].join("\n\n");
      if (candidate.length > maxChars) {
        batches.push(cur.join("\n\n"));
        cur = [p];
        continue;
      }
    }
    cur.push(p);
  }

  if (cur.length > 0) {
    batches.push(cur.join("\n\n"));
  }
  return batches;
}
