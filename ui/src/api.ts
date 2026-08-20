export type ConnectionStatus = {
  configured: boolean;
  account: string;
  user: string;
  database: string;
  schema: string;
  privateKeyConfigured: boolean;
};

export type TableSummary = {
  database: string;
  schema: string;
  name: string;
  type: "BASE TABLE" | "VIEW";
  descriptionStatus: "strong" | "weak" | "missing";
};

export type TableListRequest = {
  warehouse: string;
  database: string;
  schema: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");

const demoConnection: ConnectionStatus = {
  configured: true,
  account: "demo-account",
  user: "agent_user",
  database: "ANALYTICS",
  schema: "PUBLIC",
  privateKeyConfigured: true,
};

const demoSchemas = ["PUBLIC", "CORE", "MARTS", "SANDBOX"];
const demoTables: TableSummary[] = [
  {
    database: "ANALYTICS",
    schema: "PUBLIC",
    name: "ORDERS",
    type: "BASE TABLE",
    descriptionStatus: "weak",
  },
  {
    database: "ANALYTICS",
    schema: "PUBLIC",
    name: "CUSTOMERS",
    type: "BASE TABLE",
    descriptionStatus: "strong",
  },
  {
    database: "ANALYTICS",
    schema: "PUBLIC",
    name: "ORDER_REPORTING_SAMPLE",
    type: "BASE TABLE",
    descriptionStatus: "missing",
  },
];

export async function getConnectionStatus(): Promise<ConnectionStatus> {
  return getJson<ConnectionStatus>("/api/connection/status", demoConnection);
}

export async function listWarehouses(): Promise<string[]> {
  return getRequiredJson<string[]>("/api/snowflake/warehouses");
}

export async function listSchemas(warehouse: string): Promise<string[]> {
  const search = new URLSearchParams({ warehouse });
  return getJson<string[]>(`/api/snowflake/schemas?${search.toString()}`, demoSchemas);
}

export async function listTables(request: TableListRequest): Promise<TableSummary[]> {
  const search = new URLSearchParams({
    warehouse: request.warehouse,
    database: request.database,
    schema: request.schema,
  });
  return getJson<TableSummary[]>(`/api/snowflake/tables?${search.toString()}`, demoTables);
}

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const url = apiBaseUrl ? `${apiBaseUrl}${path}` : path;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (apiBaseUrl) {
      throw error;
    }
    await pause();
    return fallback;
  }
}

async function getRequiredJson<T>(path: string): Promise<T> {
  const url = apiBaseUrl ? `${apiBaseUrl}${path}` : path;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

function pause(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 220));
}
