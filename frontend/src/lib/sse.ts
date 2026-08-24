/**
 * Manual Server-Sent-Events parsing over `fetch` + a ReadableStream reader.
 *
 * EventSource only supports GET, and the chat endpoint is a POST, so we read the
 * body stream directly. sse-starlette may use CRLF separators and emits periodic
 * `: ping` comment frames, so the parser is separator-agnostic and comment-aware.
 * Dispatch is on the JSON payload's `type` field (guaranteed by the schema),
 * not the SSE `event:` line.
 */

/** One parsed SSE frame's data payload, or null for comment/keep-alive frames. */
function parseFrame(frame: string): string | null {
  const dataLines: string[] = [];
  for (const rawLine of frame.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "" || line.startsWith(":")) continue; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "data") dataLines.push(value);
  }
  return dataLines.length > 0 ? dataLines.join("\n") : null;
}

/**
 * Consume an SSE response body, yielding each frame's JSON `data` payload parsed
 * as `T`. Callers discriminate on the payload's own `type` field.
 */
export async function* readSSE<T>(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<T> {
  if (!response.body) {
    throw new Error("Response has no readable body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const data = parseFrame(frame);
        if (data === null) continue;
        yield JSON.parse(data) as T;
      }
    }

    // Flush any trailing frame that lacked a terminating blank line.
    const tail = parseFrame(buffer.replace(/\r\n/g, "\n"));
    if (tail !== null) {
      yield JSON.parse(tail) as T;
    }
  } finally {
    reader.cancel().catch(() => {
      /* reader already closed */
    });
  }
}
