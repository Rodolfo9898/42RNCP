// A fake web app for the extension: answers `fetch` from a table of routes ("METHOD route", the route is what follows /api/) and
// records every request, so a test can say which routes of the REST API the extension called, with what.

export interface Recorded { method: string; route: string; body: unknown; form?: FormData }
type Answer = unknown | ((request: Recorded) => unknown);

export class FakeApp {
  readonly requests: Recorded[] = [];
  private readonly routes = new Map<string, { answer: Answer; status: number }>();

  /** `answer` is the JSON body (or a function of the request that makes it; a string or a Buffer is sent as it is: text, an image);
   * `status` is the HTTP status. */
  on(key: string, answer: Answer, status = 200): this {
    this.routes.set(key, { answer, status });
    return this;
  }

  /** Requests whose "METHOD route" is `key`. */
  calls(key: string): Recorded[] {
    return this.requests.filter((r) => `${r.method} ${r.route}` === key);
  }

  readonly fetch = async (input: string | URL | Request, init: RequestInit = {}): Promise<Response> => {
    const url = String(input);
    const route = url.slice(url.indexOf("/api/") + "/api/".length);
    const method = init.method || "GET";
    const request: Recorded = { method, route, body: null };
    if (typeof init.body === "string") request.body = JSON.parse(init.body);
    else if (init.body instanceof FormData) request.form = init.body;
    this.requests.push(request);
    const found = this.routes.get(`${method} ${route}`);
    if (!found) return Response.json({ detail: `unexpected ${method} ${url}` }, { status: 404 });
    const body = typeof found.answer === "function" ? (found.answer as (r: Recorded) => unknown)(request) : found.answer;
    return typeof body === "string" || body instanceof Buffer ? new Response(body, { status: found.status }) : Response.json(body, { status: found.status });
  };

  /** Makes it the `fetch` of the process; the returned function puts the real one back. */
  install(): () => void {
    const real = globalThis.fetch;
    globalThis.fetch = this.fetch as typeof fetch;
    return () => { globalThis.fetch = real; };
  }
}
