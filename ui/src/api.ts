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

export type DescriptionAnalysisColumn = {
  table_identifier: string;
  column_name: string;
  raw_column: string;
  description: string | null;
  result: {
    has_description: boolean;
    quality: "missing" | "weak" | "adequate" | "strong";
    score: number;
    issues: string[];
    recommendation: string | null;
  };
};

export type DescriptionAnalysisTable = {
  table_identifier: string;
  table_description: string | null;
  table_result: DescriptionAnalysisColumn["result"];
  columns: DescriptionAnalysisColumn[];
};

export type MetadataDescriptionAnalysis = {
  tables: DescriptionAnalysisTable[];
  total_tables: number;
  total_columns: number;
  described_columns: number;
  missing_column_descriptions: number;
  weak_column_descriptions: number;
  adequate_column_descriptions: number;
  strong_column_descriptions: number;
};

export type ColumnDescriptionUpdate = {
  name: string;
  description: string;
};

export type SaveColumnDescriptionsRequest = {
  database: string;
  schema: string;
  table: string;
  columns: ColumnDescriptionUpdate[];
};

export type SaveColumnDescriptionsResponse = {
  status: "scaffolded";
  persisted: boolean;
  columnsReceived: number;
};

export type ColumnDescriptionSuggestion = {
  name: string;
  suggestedDescription: string;
  reason: string;
};

export type MetadataDescriptionSuggestions = {
  status: "suggested";
  model: string;
  table: string;
  suggestions: ColumnDescriptionSuggestion[];
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

export async function runMetadataDescriptionAnalysis(
  metadata: TableMetadata,
): Promise<MetadataDescriptionAnalysis> {
  return postRequiredJson<MetadataDescriptionAnalysis>("/metadata/description-analysis", {
    tables: [
      {
        database: metadata.database,
        schema: metadata.schema,
        name: metadata.table,
        kind: "TABLE",
        description: null,
        columns: metadata.columns.map(formatColumnForAnalysis),
        context_markdown: "",
      },
    ],
  });
}

export async function saveColumnDescriptions(
  request: SaveColumnDescriptionsRequest,
): Promise<SaveColumnDescriptionsResponse> {
  return postRequiredJson<SaveColumnDescriptionsResponse>("/api/snowflake/column-descriptions", request);
}

export async function suggestColumnDescriptions(
  metadata: TableMetadata,
): Promise<MetadataDescriptionSuggestions> {
  return postRequiredJson<MetadataDescriptionSuggestions>("/api/snowflake/description-suggestions", metadata);
}

async function getRequiredJson<T>(path: string): Promise<T> {
  const url = apiBaseUrl ? `${apiBaseUrl}${path}` : path;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return (await response.json()) as T;
}

async function postRequiredJson<T>(path: string, body: object): Promise<T> {
  const url = apiBaseUrl ? `${apiBaseUrl}${path}` : path;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return (await response.json()) as T;
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail) {
      return payload.detail;
    }
  } catch {
    // Fall through to the generic status message when the response is not JSON.
  }
  return `Request failed with ${response.status}`;
}

function formatColumnForAnalysis(column: ColumnMetadata): string {
  const dataType = column.dataType ? ` ${column.dataType}` : "";
  const description = column.description ? ` -- ${column.description}` : "";
  return `${column.name}${dataType}${description}`;
}
