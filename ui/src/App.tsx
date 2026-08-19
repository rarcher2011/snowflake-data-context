import { useEffect, useMemo, useState } from "react";

import {
  ConnectionStatus,
  TableSummary,
  getConnectionStatus,
  listSchemas,
  listTables,
  listWarehouses,
} from "./api";

type LoadState = "idle" | "loading" | "ready" | "error";

export default function App() {
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [warehouses, setWarehouses] = useState<string[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [selectedWarehouse, setSelectedWarehouse] = useState("");
  const [selectedSchema, setSelectedSchema] = useState("");
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [startupState, setStartupState] = useState<LoadState>("idle");
  const [tableState, setTableState] = useState<LoadState>("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadStartupData() {
      setStartupState("loading");
      setMessage("");
      try {
        const [connectionStatus, warehouseOptions] = await Promise.all([
          getConnectionStatus(),
          listWarehouses(),
        ]);
        if (cancelled) {
          return;
        }
        const initialWarehouse = warehouseOptions[0] ?? "";
        const schemaOptions = initialWarehouse ? await listSchemas(initialWarehouse) : [];
        if (cancelled) {
          return;
        }
        setConnection(connectionStatus);
        setWarehouses(warehouseOptions);
        setSelectedWarehouse(initialWarehouse);
        setSchemas(schemaOptions);
        setSelectedSchema(connectionStatus.schema || schemaOptions[0] || "");
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
      if (!selectedWarehouse) {
        setSchemas([]);
        setSelectedSchema("");
        return;
      }
      try {
        const schemaOptions = await listSchemas(selectedWarehouse);
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
  }, [selectedWarehouse]);

  const connectionLabel = useMemo(() => {
    if (!connection) {
      return "Checking";
    }
    return connection.configured && connection.privateKeyConfigured ? "Ready" : "Needs setup";
  }, [connection]);

  async function runTableList() {
    if (!connection || !selectedWarehouse || !selectedSchema) {
      return;
    }
    setTableState("loading");
    setMessage("");
    try {
      const tableResults = await listTables({
        warehouse: selectedWarehouse,
        database: connection.database,
        schema: selectedSchema,
      });
      setTables(tableResults);
      setTableState("ready");
    } catch (error) {
      setTableState("error");
      setMessage(error instanceof Error ? error.message : "Unable to list tables.");
    }
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Snowflake Data Context</p>
          <h1>Agent Workspace</h1>
        </div>
        <div className={`status-pill ${connectionLabel === "Ready" ? "is-ready" : ""}`}>
          <span aria-hidden="true" />
          {connectionLabel}
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
              <dt>User</dt>
              <dd>{connection?.user ?? "-"}</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>{connection?.database ?? "-"}</dd>
            </div>
            <div>
              <dt>Private key</dt>
              <dd>{connection?.privateKeyConfigured ? "Configured" : "Missing"}</dd>
            </div>
          </dl>
        </div>

        <div className="panel controls-panel">
          <div className="panel-heading">
            <h2>Scope</h2>
            <p>Warehouse and schema</p>
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
            </div>
            {tables.map((table) => (
              <div className="table-row" role="row" key={`${table.database}.${table.schema}.${table.name}`}>
                <span role="cell">{table.name}</span>
                <span role="cell">{table.type}</span>
                <span role="cell" className={`quality quality-${table.descriptionStatus}`}>
                  {table.descriptionStatus}
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
      </section>
    </main>
  );
}
