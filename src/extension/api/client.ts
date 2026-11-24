/** An answer the app refused, or no answer at all (`status` is then undefined): the message is what a person can read. */
export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

export interface JsonRequest { method?: string; body?: unknown; form?: FormData }

/** Gateway to the web app (VERDICT_API): JSON in and out, binary pages, text, and every failure as an ApiError. */
export class ApiClient {
  constructor(private readonly base: string, private readonly fetcher: typeof fetch = (input, init) => fetch(input, init)) {}

  async json<T>(route: string, { method = "GET", body, form }: JsonRequest = {}): Promise<T> {
    const init: RequestInit = { method, headers: {} };
    if (form) init.body = form;
    else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "content-type": "application/json" }; }
    const response = await this.send(route, init);
    const text = await response.text();
    let data: unknown = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!response.ok) {
      const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : data;
      throw new ApiError(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`, response.status);
    }
    return data as T;
  }

  /** A binary answer (a page of a subject PDF as an image). */
  async bytes(route: string): Promise<Buffer> {
    return Buffer.from(await (await this.ok(route)).arrayBuffer());
  }

  async text(route: string): Promise<string> {
    return (await this.ok(route)).text();
  }

  private async ok(route: string): Promise<Response> {
    const response = await this.send(route, { method: "GET" });
    if (!response.ok) throw new ApiError(`${response.status} ${response.statusText}`, response.status);
    return response;
  }

  private async send(route: string, init: RequestInit): Promise<Response> {
    try {
      return await this.fetcher(`${this.base}/api/${route}`, init);
    } catch (err) {
      throw new ApiError(`the Verdict service (${this.base}) cannot be reached: ${(err as Error).message}`);
    }
  }
}
