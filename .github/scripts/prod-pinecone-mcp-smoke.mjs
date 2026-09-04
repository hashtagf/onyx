const MCP_ENDPOINT =
  process.env.MCP_ENDPOINT ?? "http://127.0.0.1:8000/mcp";
const MCP_REQUEST_TIMEOUT_MS = 45_000;
const PROTOCOL_VERSION = "2025-03-26";
const SEARCH_TEXT = "ข้อมูล";
const EXPECTED_TOOL_NAMES = [
  "describe-index",
  "describe-index-stats",
  "list-indexes",
  "search-records",
];

let sessionId;
let nextRequestId = 1;

function parseResponseBody(body, contentType) {
  if (!body.trim()) {
    return [];
  }

  if (!contentType.includes("text/event-stream")) {
    return [JSON.parse(body)];
  }

  return body
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .filter((data) => data && data !== "[DONE]")
    .map((data) => JSON.parse(data));
}

async function sendRequest(method, params = {}, notification = false) {
  const id = notification ? undefined : nextRequestId++;
  const headers = {
    Accept: "application/json, text/event-stream",
    "Content-Type": "application/json",
  };
  if (sessionId) {
    headers["Mcp-Session-Id"] = sessionId;
  }

  const response = await fetch(MCP_ENDPOINT, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      ...(id === undefined ? {} : { id }),
      method,
      params,
    }),
    signal: AbortSignal.timeout(MCP_REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`MCP ${method} returned HTTP ${response.status}`);
  }

  sessionId ??= response.headers.get("mcp-session-id") ?? undefined;
  const body = await response.text();
  if (notification) {
    return undefined;
  }

  const messages = parseResponseBody(
    body,
    response.headers.get("content-type") ?? ""
  );
  const message = messages.find((item) => item.id === id);
  if (!message) {
    throw new Error(`MCP ${method} did not return request ${id}`);
  }
  if (message.error) {
    throw new Error(`MCP ${method} returned a JSON-RPC error`);
  }
  return message.result;
}

async function callTool(name, args = {}) {
  const result = await sendRequest("tools/call", {
    name,
    arguments: args,
  });
  if (result?.isError) {
    throw new Error(`Pinecone tool ${name} returned an error`);
  }

  const text = result?.content?.find((item) => item.type === "text")?.text;
  if (!text) {
    throw new Error(`Pinecone tool ${name} returned no text result`);
  }
  return JSON.parse(text);
}

await sendRequest("initialize", {
  protocolVersion: PROTOCOL_VERSION,
  capabilities: {},
  clientInfo: {
    name: "onyx-prod-smoke",
    version: "1.0.0",
  },
});
await sendRequest("notifications/initialized", {}, true);

const listedTools = await sendRequest("tools/list");
const tools = listedTools?.tools ?? [];
const toolNames = tools.map((tool) => tool.name).sort();
if (toolNames.join("\n") !== EXPECTED_TOOL_NAMES.join("\n")) {
  throw new Error("Pinecone MCP does not expose the expected read-only tools");
}
if (tools.some((tool) => tool.annotations?.readOnlyHint !== true)) {
  throw new Error("Pinecone MCP exposes a tool without the read-only annotation");
}

const listedIndexes = await callTool("list-indexes");
const indexes = listedIndexes?.indexes ?? [];
if (!indexes.length) {
  throw new Error("Pinecone has no indexes");
}

let searchableIndex;
let searchableNamespace;
for (const index of indexes) {
  const description = await callTool("describe-index", { name: index.name });
  const isCompatibleStandardIndex =
    !description?.embed && description?.dimension === 1024;
  if (!description?.status?.ready || !isCompatibleStandardIndex) {
    continue;
  }

  const stats = await callTool("describe-index-stats", {
    name: description.name,
  });
  const namespaces = Object.entries(stats?.namespaces ?? {}).sort(
    ([, left], [, right]) =>
      (right?.recordCount ?? 0) - (left?.recordCount ?? 0)
  );
  const [namespace = "", namespaceStats] = namespaces[0] ?? [];
  if ((namespaceStats?.recordCount ?? 0) > 0) {
    searchableIndex = description;
    searchableNamespace = namespace;
    break;
  }
}
if (!searchableIndex) {
  throw new Error(
    "Pinecone has no ready populated standard index with a compatible embedding"
  );
}

const query = {
  topK: 3,
  inputs: { text: SEARCH_TEXT },
};
const search = await callTool("search-records", {
  name: searchableIndex.name,
  namespace: searchableNamespace,
  query,
});
const hits = search?.result?.hits ?? search?.hits ?? [];
if (!Array.isArray(hits) || hits.length === 0) {
  throw new Error("Pinecone search-records returned no hits");
}
if (
  !hits.some(
    (hit) =>
      typeof hit?.fields?.content_preview === "string" &&
      hit.fields.content_preview.trim().length > 0
  )
) {
  throw new Error("Pinecone search-records returned no grounding text");
}

console.log(
  `Pinecone MCP smoke passed: ${tools.length} tools, ${indexes.length} indexes, ${hits.length} grounded search hits.`
);
