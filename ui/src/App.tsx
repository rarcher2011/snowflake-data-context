import { useEffect, useState } from "react";

import {
  ConnectionStatus,
  MetadataDescriptionAnalysis,
  TableMetadata,
  TableSummary,
  getTableMetadata,
  getConnectionStatus,
  listDatabases,
  listSchemas,
  listTables,
  listWarehouses,
  runMetadataDescriptionAnalysis,
} from "./api";

type LoadState = "idle" | "loading" | "ready" | "error";
type AppView = "home" | "metadata";

const metadataHash = "#metadata";

export default function App() {
  const [activeView, setActiveView] = useState<AppView>(() =>
    window.location.hash === metadataHash ? "metadata" : "home",
  );
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
  const [analysisState, setAnalysisState] = useState<LoadState>("idle");
  const [analysisResult, setAnalysisResult] = useState<MetadataDescriptionAnalysis | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    function syncViewFromHash() {
      setActiveView(window.location.hash === metadataHash ? "metadata" : "home");
    }

    window.addEventListener("hashchange", syncViewFromHash);
    window.addEventListener("popstate", syncViewFromHash);

    return () => {
      window.removeEventListener("hashchange", syncViewFromHash);
      window.removeEventListener("popstate", syncViewFromHash);
    };
  }, []);

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
    if (!selectedWarehouse || !selectedDatabase || !selectedSchema) {
      setTableState("error");
      setMessage(
        missingSelectionMessage({
          warehouse: selectedWarehouse,
          database: selectedDatabase,
          schema: selectedSchema,
        }),
      );
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
      setAnalysisResult(null);
      setAnalysisState("idle");
      setMetadataState("ready");
      openView("metadata");
    } catch (error) {
      setMetadataState("error");
      setMessage(error instanceof Error ? error.message : "Unable to load table metadata.");
    }
  }

  async function runAnalysis() {
    if (!selectedMetadata) {
      setMessage("Select table metadata before running analysis.");
      return;
    }
    openView("metadata");
    setAnalysisState("loading");
    setMessage("");
    try {
      const analysis = await runMetadataDescriptionAnalysis(selectedMetadata);
      setAnalysisResult(analysis);
      setAnalysisState("ready");
    } catch (error) {
      setAnalysisState("error");
      setMessage(error instanceof Error ? error.message : "Unable to run metadata analysis.");
    }
  }

  function openView(view: AppView) {
    setActiveView(view);
    const nextHash = view === "metadata" ? metadataHash : "";
    if (window.location.hash !== nextHash) {
      history.pushState(null, "", `${window.location.pathname}${nextHash}`);
    }
  }

  const isMetadataView = activeView === "metadata";

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Workspace navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            S
          </span>
          <span>DataFlow</span>
        </div>

        <nav className="nav-groups">
          <div className="nav-group">
            <p>Workspace</p>
            <a
              className={`nav-item ${activeView === "home" ? "is-active" : ""}`}
              href="#"
              onClick={(event) => {
                event.preventDefault();
                openView("home");
              }}
            >
              Home
            </a>
            <a
              className={`nav-item ${isMetadataView ? "is-active" : ""}`}
              href={metadataHash}
              onClick={(event) => {
                event.preventDefault();
                openView("metadata");
              }}
            >
              Metadata
              <span>{tables.length}</span>
            </a>
          </div>
        </nav>

        <div className="sidebar-user">
          <span>{connection?.currentUser?.slice(0, 2) || "SF"}</span>
          <div>
            <strong>{connection?.currentUser ?? "Snowflake"}</strong>
            <p>{connection?.privateKeyConnectionWorking ? "Connected" : "Setup needed"}</p>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="top-bar">
          <div>
            <p className="breadcrumb">Workspace › Snowflake Context</p>
            <h1>{isMetadataView ? "Metadata Workspace" : "Agent Workspace"}</h1>
          </div>
          <div className="top-actions">
            <input aria-label="Search" placeholder="Search metadata..." type="search" />
            <button
              className="primary-action top-action"
              type="button"
              onClick={() => void runAnalysis()}
              disabled={!selectedMetadata || analysisState === "loading"}
            >
              {analysisState === "loading" ? "Analyzing" : "Run Analysis"}
            </button>
          </div>
        </header>

        <section
          className={`content-area ${isMetadataView ? "metadata-view" : ""}`}
          aria-label={isMetadataView ? "Snowflake metadata workspace" : "Snowflake connection workspace"}
        >
          <div className="summary-strip" aria-label="Workspace summary">
            <div>
              <p>Account</p>
              <strong>{connection?.account ?? "Snowflake"}</strong>
            </div>
            <div>
              <p>Warehouse</p>
              <strong>{selectedWarehouse || "-"}</strong>
            </div>
            <div>
              <p>Database</p>
              <strong>{selectedDatabase || connection?.database || "-"}</strong>
            </div>
            <div>
              <p>Tables</p>
              <strong>{tables.length}</strong>
            </div>
          </div>

          <div className="layout-grid">
            {!isMetadataView ? (
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
            ) : null}

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
                disabled={startupState === "loading" || tableState === "loading"}
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

            {isMetadataView ? (
              <>
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

                <div className="panel analysis-panel">
                  <div className="panel-heading">
                    <h2>Analysis</h2>
                    <p>
                      {analysisResult
                        ? `${analysisResult.total_columns} columns scored`
                        : "Description quality"}
                    </p>
                  </div>

                  {analysisState === "loading" ? <div className="empty-state">Running analysis</div> : null}

                  {analysisState !== "loading" && analysisResult ? (
                    <div className="analysis-content">
                      <div className="analysis-metrics">
                        <div>
                          <p>Coverage</p>
                          <strong>{formatPercent(analysisResult.described_columns, analysisResult.total_columns)}</strong>
                        </div>
                        <div>
                          <p>Missing</p>
                          <strong>{analysisResult.missing_column_descriptions}</strong>
                        </div>
                        <div>
                          <p>Weak</p>
                          <strong>{analysisResult.weak_column_descriptions}</strong>
                        </div>
                        <div>
                          <p>Strong</p>
                          <strong>{analysisResult.strong_column_descriptions}</strong>
                        </div>
                      </div>

                      <div className="analysis-list">
                        {analysisResult.tables.flatMap((table) =>
                          table.columns
                            .filter((column) => column.result.quality === "missing" || column.result.quality === "weak")
                            .map((column) => (
                              <div className="analysis-item" key={`${table.table_identifier}.${column.column_name}`}>
                                <strong>{column.column_name}</strong>
                                <span className={`quality quality-${column.result.quality}`}>
                                  {column.result.quality}
                                </span>
                                <p>{column.result.recommendation ?? column.result.issues.join("; ")}</p>
                              </div>
                            )),
                        )}
                        {analysisResult.missing_column_descriptions === 0 &&
                        analysisResult.weak_column_descriptions === 0 ? (
                          <div className="empty-state">No weak or missing descriptions found</div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {analysisState !== "loading" && !analysisResult ? (
                    <div className="empty-state">Run analysis after selecting metadata</div>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}

function formatPercent(described: number, total: number): string {
  if (total === 0) {
    return "100%";
  }
  return `${Math.round((described / total) * 100)}%`;
}

function missingSelectionMessage(selections: {
  warehouse: string;
  database: string;
  schema: string;
}): string {
  const missing = [
    selections.warehouse ? null : "warehouse",
    selections.database ? null : "database",
    selections.schema ? null : "schema",
  ].filter((selection) => selection !== null);

  return `Select a ${missing.join(", ")} before running the table list.`;
}
