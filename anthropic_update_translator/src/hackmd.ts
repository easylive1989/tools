const API_URL = "https://api.hackmd.io/v1/notes";

interface CreateNoteResponse {
  id?: string;
  publishLink?: string;
}

export class HackMdClient {
  constructor(private token: string) {}

  async createNote(content: string): Promise<{ publishLink: string }> {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        content,
        readPermission: "guest",
        writePermission: "owner",
        commentPermission: "disabled",
      }),
    });

    if (!res.ok) {
      throw new Error(`HackMD createNote failed: ${res.status} ${await res.text()}`);
    }

    const data = (await res.json()) as CreateNoteResponse;
    if (!data.publishLink) {
      throw new Error(`HackMD response missing publishLink: ${JSON.stringify(data)}`);
    }
    return { publishLink: data.publishLink };
  }
}
