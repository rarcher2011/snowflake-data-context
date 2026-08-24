import { useEffect, useState } from "react";

import {
  ConnectionStatus,
  TableMetadata,
  TableSummary,
  getTableMetadata,
  getConnectionStatus,
  listDatabases,
  listSchemas,
  listTables,
  listWarehouses,
} from "./api";

type LoadState = "idle" | "loading" | "ready" | "error";

export default function App() {
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [databases, setDatabases] = useState<string[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [selectedWarehouse, setSelectedWarehouse] = useState("");
  const [selectedDatabase, setSelectedDatabase] = useState("");
  const [selectedSchema, setSelectedSchema] = useState("");
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [selectedMetadata, setSelectedMetadata] = useState<TableMetadata | null>(null);
  const [startupState, setStartupState] = useState<LoadState>("idle");
  const [tableState, setTableState] = useState<LoadState>("idle");
  const [metadataState, setMetadataState] = useState<LoadState>("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadStartupData() {
      setStartupState("loading");
      setMessage("");
      try {
        const connectionStatus = await getConnectionStatus();
        if (cancelled) {
          return;
        }
        setConnection(connectionStatus);

        let warehouseOptions: string[] = [];
        try {
          warehouseOptions = await listWarehouses();
        } catch (error) {
          if (cancelled) {
            return;
          }
          setWarehouses([]);
          setDatabases([]);
          setSchemas([]);
          setSelectedWarehouse("");
          setSelectedDatabase(connectionStatus.database === "Not selected" ? "" : connectionStatus.database);
          setSelectedSchema(connectionStatus.schema === "Not selected" ? "" : connectionStatus.schema);
          setStartupState("ready");
          setMessage(error instanceof Error ? error.message : "Unable to load warehouses.");
          return;
        }

        const databaseOptions = await listDatabases();
        const initialWarehouse = warehouseOptions[0] ?? "";
        const initialDatabase =
          connectionStatus.database !== "Not selected" && databaseOptions.includes(connectionStatus.database)
            ? connectionStatus.database
            : databaseOptions[0] ?? "";
        const schemaOptions =
          initialWarehouse && initialDatabase ? await listSchemas(initialWarehouse, initialDatabase) : [];
        if (cancelled) {
          return;
        }
        setWarehouses(warehouseOptions);
        setDatabases(databaseOptions);
        setSelectedWarehouse(initialWarehouse);
        setSelectedDatabase(initialDatabase);
        setSchemas(schemaOptions);
        setSelectedSchema(
          connectionStatus.schema === "Not selected"
            ? schemaOptions[0] || ""
            : connectionStatus.schema || schemaOptions[0] || "",
        );
        setStartupState("ready");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setStartupState("error");
        setMessage(error instanceof Error ? error.message : "Unable to load connection setup.");
      }
    }

    void loadStartupData();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function refreshSchemas() {
      if (!selectedWarehouse || !selectedDatabase) {
        setSchemas([]);
        setSelectedSchema("");
        return;
      }
      try {
        const schemaOptions = await listSchemas(selectedWarehouse, selectedDatabase);
        if (cancelled) {
          return;
        }
        setSchemas(schemaOptions);
        setSelectedSchema((current) =>
          schemaOptions.includes(current) ? current : schemaOptions[0] ?? "",
        );
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSchemas([]);
        setSelectedSchema("");
        setMessage(error instanceof Error ? error.message : "Unable to load schemas.");
      }
    }

    void refreshSchemas();

    return () => {
      cancelled = true;
    };
  }, [selectedWarehouse, selectedDatabase]);

  async function runTableList() {
    if (!connection || !selectedWarehouse || !selectedDatabase || !selectedSchema) {
      return;
    }
    setTableState("loading");
    setMessage("");
    try {
      const tableResults = await listTables({
        warehouse: selectedWarehouse,
        database: selectedDatabase,
        schema: selectedSchema,
      });
      setTables(tableResults);
      setSelectedMetadata(null);
      setMetadataState("idle");
      setTableState("ready");
    } catch (error) {
      setTableState("error");
      setMessage(error instanceof Error ? error.message : "Unable to list tables.");
    }
  }

  async function selectTableMetadata(table: TableSummary) {
    if (!selectedWarehouse || !selectedDatabase || !selectedSchema || !table.name) {
      return;
    }
    setMetadataState("loading");
    setMessage("");
    try {
      const metadata = await getTableMetadata({
        warehouse: selectedWarehouse,
        database: selectedDatabase,
        schema: selectedSchema,
        table: table.name,
      });
      setSelectedMetadata(metadata);
      setMetadataState("ready");
    } catch (error) {
      setMetadataState("error");
      setMessage(error instanceof Error ? error.message : "Unable to load table metadata.");
    }
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Snowflake Data Context</p>
          <h1>Agent Workspace</h1>
        </div>
      </header>

      <section className="layout-grid" aria-label="Snowflake connection workspace">
        <div className="panel connection-panel">
          <div className="panel-heading">
            <h2>Connection</h2>
            <p>{connection?.account ?? "Snowflake account"}</p>
          </div>

          <dl className="connection-list">
            <div>
              <dt>Current user</dt>
              <dd>{connection?.currentUser ?? "-"}</dd>
            </div>
            <div>
              <dt>Database selected</dt>
              <dd>{selectedDatabase || connection?.database || "-"}</dd>
            </div>
            <div>
              <dt>Private key connection</dt>
              <dd>
                {connection?.privateKeyConnectionWorking
                  ? "Working"
                  : connection?.privateKeyConfigured
                    ? "Configured, not connected"
                    : "Missing"}
              </dd>
            </div>
            {connection?.error ? (
              <div>
                <dt>Status</dt>
                <dd>{connection.error}</dd>
              </div>
            ) : null}
          </dl>
        </div>

        <div className="panel controls-panel">
          <div className="panel-heading">
            <h2>Scope</h2>
            <p>Warehouse, database, and schema</p>
          </div>

          <label>
            <span>Warehouse</span>
            <select
              value={selectedWarehouse}
              onChange={(event) => setSelectedWarehouse(event.target.value)}
              disabled={startupState === "loading"}
            >
              {warehouses.map((warehouse) => (
                <option key={warehouse} value={warehouse}>
                  {warehouse}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Database</span>
            <select
              value={selectedDatabase}
              onChange={(event) => setSelectedDatabase(event.target.value)}
              disabled={startupState === "loading" || databases.length === 0}
            >
              {databases.map((database) => (
                <option key={database} value={database}>
                  {database}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Schema</span>
            <select
              value={selectedSchema}
              onChange={(event) => setSelectedSchema(event.target.value)}
              disabled={startupState === "loading" || schemas.length === 0}
            >
              {schemas.map((schema) => (
                <option key={schema} value={schema}>
                  {schema}
                </option>
              ))}
            </select>
          </label>

          <button
            className="primary-action"
            type="button"
            onClick={() => void runTableList()}
            disabled={startupState !== "ready" || tableState === "loading"}
          >
            {tableState === "loading" ? "Running" : "Run Table List"}
          </button>
        </div>

        <div className="panel table-panel">
          <div className="panel-heading">
            <h2>Tables</h2>
            <p>{tableState === "ready" ? `${tables.length} returned` : "Quick test"}</p>
          </div>

          {message ? <p className="inline-error">{message}</p> : null}

          <div className="table-list" role="table" aria-label="Snowflake tables">
            <div className="table-row table-header" role="row">
              <span role="columnheader">Name</span>
              <span role="columnheader">Type</span>
              <span role="columnheader">Descriptions</span>
              <span role="columnheader">Metadata</span>
            </div>
            {tables.map((table) => (
              <div className="table-row" role="row" key={`${table.database}.${table.schema}.${table.name}`}>
                <span role="cell">{table.name}</span>
                <span role="cell">{table.type}</span>
                <span role="cell" className={`quality quality-${table.descriptionStatus}`}>
                  {table.descriptionStatus}
                </span>
                <span role="cell">
                  <button
                    className="metadata-action"
                    type="button"
                    onClick={() => void selectTableMetadata(table)}
                    disabled={metadataState === "loading"}
                  >
                    Metadata
                  </button>
                </span>
              </div>
            ))}
            {tables.length === 0 ? (
              <div className="empty-state">
                {tableState === "loading" ? "Loading tables" : "No table list run yet"}
              </div>
            ) : null}
          </div>
        </div>

        <div className="panel metadata-panel">
          <div className="panel-heading">
            <h2>Metadata</h2>
            <p>
              {selectedMetadata
                ? `${selectedMetadata.database}.${selectedMetadata.schema}.${selectedMetadata.table}`
                : "Selected table"}
            </p>
          </div>

          {metadataState === "loading" ? <div className="empty-state">Loading metadata</div> : null}

          {metadataState !== "loading" && selectedMetadata ? (
            <div className="metadata-list" role="table" aria-label="Selected table metadata">
              <div className="metadata-row metadata-header" role="row">
                <span role="columnheader">Field</span>
                <span role="columnheader">Schema</span>
                <span role="columnheader">Description</span>
              </div>
              {selectedMetadata.columns.map((column) => (
                <div className="metadata-row" role="row" key={column.name}>
                  <span role="cell">{column.name}</span>
                  <span role="cell">
                    {column.dataType}
                    {column.nullable ? ` · ${column.nullable === "YES" ? "nullable" : "required"}` : ""}
                  </span>
                  <span role="cell">{column.description || "No description"}</span>
                </div>
              ))}
            </div>
          ) : null}

          {metadataState !== "loading" && !selectedMetadata ? (
            <div className="empty-state">Select metadata from a table</div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
