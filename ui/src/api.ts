export type ConnectionStatus = {
  configured: boolean;
  account: string;
  configuredUser: string;
  currentUser: string;
  database: string;
  schema: string;
  privateKeyConfigured: boolean;
  privateKeyConnectionWorking: boolean;
  error: string | null;
};

export type TableSummary = {
  database: string;
  schema: string;
  name: string;
  type: "BASE TABLE" | "VIEW";
  descriptionStatus: "strong" | "weak" | "missing";
};

export type ColumnMetadata = {
  name: string;
  dataType: string;
  description: string;
  nullable: string;
};

export type TableMetadata = {
  database: string;
  schema: string;
  table: string;
  columns: ColumnMetadata[];
};

export type TableListRequest = {
  warehouse: string;
  database: string;
  schema: string;
};

export type TableMetadataRequest = TableListRequest & {
  table: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");

export async function getConnectionStatus(): Promise<ConnectionStatus> {
  return getRequiredJson<ConnectionStatus>("/api/connection/status");
}

export async function listWarehouses(): Promise<string[]> {
  return getRequiredJson<string[]>("/api/snowflake/warehouses");
}

export async function listDatabases(): Promise<string[]> {
  return getRequiredJson<string[]>("/api/snowflake/databases");
}

export async function listSchemas(warehouse: string, database: string): Promise<string[]> {
  const search = new URLSearchParams({ warehouse, database });
  return getRequiredJson<string[]>(`/api/snowflake/schemas?${search.toString()}`);
}

export async function listTables(request: TableListRequest): Promise<TableSummary[]> {
  const search = new URLSearchParams({
    warehouse: request.warehouse,
    database: request.database,
    schema: request.schema,
  });
  return getRequiredJson<TableSummary[]>(`/api/snowflake/tables?${search.toString()}`);
}

export async function getTableMetadata(request: TableMetadataRequest): Promise<TableMetadata> {
  const search = new URLSearchParams({
    warehouse: request.warehouse,
    database: request.database,
    schema: request.schema,
    table: request.table,
  });
  return getRequiredJson<TableMetadata>(`/api/snowflake/table-metadata?${search.toString()}`);
}

async function getRequiredJson<T>(path: string): Promise<T> {
  const url = apiBaseUrl ? `${apiBaseUrl}${path}` : path;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}
