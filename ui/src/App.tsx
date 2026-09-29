import { useEffect, useRef, useState } from "react";

import {
  ConnectionStatus,
  DescriptionAnalysisColumn,
  DiscoveryReportResult,
  MetadataDescriptionAnalysis,
  PlainTextTableQueryResult,
  TableMetadata,
  TableSummary,
  getTableMetadata,
  getConnectionStatus,
  listDatabases,
  listSchemas,
  listTables,
  listWarehouses,
  runDiscoveryReport,
  runPlainTextTableQuery,
  runMetadataDescriptionAnalysis,
  saveColumnDescriptions,
  suggestColumnDescriptions,
} from "./api";

type LoadState = "idle" | "loading" | "ready" | "error";
type AppView = "home" | "metadata" | "query" | "discovery";

const metadataHash = "#metadata";
const queryHash = "#query";
const discoveryHash = "#discovery";

export default function App() {
  const [activeView, setActiveView] = useState<AppView>(() => {
    if (window.location.hash === metadataHash) return "metadata";
    if (window.location.hash === queryHash) return "query";
    if (window.location.hash === discoveryHash) return "discovery";
    return "home";
  });
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
  const [saveState, setSaveState] = useState<LoadState>("idle");
  const [suggestionState, setSuggestionState] = useState<LoadState>("idle");
  const [queryState, setQueryState] = useState<LoadState>("idle");
  const [analysisResult, setAnalysisResult] = useState<MetadataDescriptionAnalysis | null>(null);
  const [queryResult, setQueryResult] = useState<PlainTextTableQueryResult | null>(null);
  const [queryText, setQueryText] = useState("");
  const [discoveryState, setDiscoveryState] = useState<LoadState>("idle");
  const [discoveryResult, setDiscoveryResult] = useState<DiscoveryReportResult | null>(null);
  const [selectedTable, setSelectedTable] = useState<TableSummary | null>(null);
  const [editedDescriptions, setEditedDescriptions] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [toast, setToast] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function syncViewFromHash() {
      if (window.location.hash === metadataHash) setActiveView("metadata");
      else if (window.location.hash === queryHash) setActiveView("query");
      else if (window.location.hash === discoveryHash) setActiveView("discovery");
      else setActiveView("home");
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
      setSelectedTable(null);
      setSelectedMetadata(null);
      setEditedDescriptions({});
      setAnalysisResult(null);
      setMetadataState("idle");
      setAnalysisState("idle");
      setSaveState("idle");
      setSuggestionState("idle");
      setQueryState("idle");
      setQueryResult(null);
      setQueryText("");
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
      setEditedDescriptions(descriptionsByColumnName(metadata));
      setAnalysisResult(null);
      setAnalysisState("idle");
      setSaveState("idle");
      setSuggestionState("idle");
      setQueryState("idle");
      setQueryResult(null);
      setQueryText("");
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
      const analysis = await runMetadataDescriptionAnalysis(
        metadataWithEditedDescriptions(selectedMetadata, editedDescriptions),
      );
      setAnalysisResult(analysis);
      setAnalysisState("ready");
    } catch (error) {
      setAnalysisState("error");
      setMessage(error instanceof Error ? error.message : "Unable to run metadata analysis.");
    }
  }

  async function saveDescriptions() {
    if (!selectedMetadata) {
      setMessage("Select table metadata before saving descriptions.");
      return;
    }
    setSaveState("loading");
    setMessage("");
    try {
      const response = await saveColumnDescriptions({
        database: selectedMetadata.database,
        schema: selectedMetadata.schema,
        table: selectedMetadata.table,
        columns: selectedMetadata.columns.map((column) => ({
          name: column.name,
          description: editedDescriptions[column.name] ?? column.description,
        })),
      });
      setSaveState("ready");
      setMessage(
        response.persisted
          ? "Column descriptions saved."
          : `Save endpoint scaffold received ${response.columnsReceived} descriptions.`,
      );
    } catch (error) {
      setSaveState("error");
      setMessage(error instanceof Error ? error.message : "Unable to save descriptions.");
    }
  }

  async function suggestDescriptions() {
    if (!selectedMetadata) {
      setMessage("Select table metadata before suggesting descriptions.");
      return;
    }
    setSuggestionState("loading");
    setMessage("");
    try {
      const response = await suggestColumnDescriptions(
        metadataWithEditedDescriptions(selectedMetadata, editedDescriptions),
      );
      setEditedDescriptions((current) => ({
        ...current,
        ...Object.fromEntries(
          response.suggestions.map((suggestion) => [
            suggestion.name,
            suggestion.suggestedDescription,
          ]),
        ),
      }));
      setSuggestionState("ready");
      setSaveState("idle");
      setMessage("");
      showToast(`${response.suggestions.length} description${response.suggestions.length === 1 ? "" : "s"} suggested`);
    } catch (error) {
      setSuggestionState("error");
      setMessage("There was an issue with the LLM call. Please try again.");
    }
  }

  async function runQuery() {
    if (!selectedMetadata) {
      setMessage("Select table metadata before running a query.");
      return;
    }
    if (!selectedWarehouse) {
      setMessage("Select a warehouse before running a query.");
      return;
    }
    if (!queryText.trim()) {
      setMessage("Enter a plain-text question before running a query.");
      return;
    }

    setQueryState("loading");
    setMessage("");
    try {
      const result = await runPlainTextTableQuery({
        ...metadataWithEditedDescriptions(selectedMetadata, editedDescriptions),
        warehouse: selectedWarehouse,
        question: queryText.trim(),
      });
      setQueryResult(result);
      setQueryState("ready");
    } catch (error) {
      setQueryState("error");
      setMessage(error instanceof Error ? error.message : "Unable to run query.");
    }
  }

  function updateEditedDescription(columnName: string, description: string) {
    setEditedDescriptions((current) => ({
      ...current,
      [columnName]: description,
    }));
    setSaveState("idle");
  }

  async function runDiscovery() {
    if (!selectedWarehouse || !selectedDatabase || !selectedSchema) {
      setMessage(
        missingSelectionMessage({
          warehouse: selectedWarehouse,
          database: selectedDatabase,
          schema: selectedSchema,
        }),
      );
      return;
    }
    setDiscoveryState("loading");
    setMessage("");
    try {
      const result = await runDiscoveryReport(selectedWarehouse, selectedDatabase, selectedSchema);
      setDiscoveryResult(result);
      setDiscoveryState("ready");
    } catch (error) {
      setDiscoveryState("error");
      setMessage(error instanceof Error ? error.message : "Unable to run discovery report.");
    }
  }

  function showToast(text: string) {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(text);
    toastTimer.current = setTimeout(() => setToast(""), 3500);
  }

  function openView(view: AppView) {
    setActiveView(view);
    const nextHash =
      view === "metadata" ? metadataHash
      : view === "query" ? queryHash
      : view === "discovery" ? discoveryHash
      : "";
    if (window.location.hash !== nextHash) {
      history.pushState(null, "", `${window.location.pathname}${nextHash}`);
    }
  }

  const isMetadataView = activeView === "metadata";
  const isQueryView = activeView === "query";
  const isDiscoveryView = activeView === "discovery";
  const analysisByColumn = buildAnalysisByColumnName(analysisResult);

  return (
    <main className="app-shell">
      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <span className="toast-icon">✓</span>
          {toast}
        </div>
      )}
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
            <a
              className={`nav-item ${isQueryView ? "is-active" : ""}`}
              href={queryHash}
              onClick={(event) => {
                event.preventDefault();
                openView("query");
              }}
            >
              Query
            </a>
            <a
              className={`nav-item ${isDiscoveryView ? "is-active" : ""}`}
              href={discoveryHash}
              onClick={(event) => {
                event.preventDefault();
                openView("discovery");
              }}
            >
              Discovery
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
            <h1>
              {isMetadataView
                ? "Metadata Workspace"
                : isQueryView
                  ? "Query Workspace"
                  : isDiscoveryView
                    ? "Discovery"
                    : "Agent Workspace"}
            </h1>
          </div>
        </header>

        <section
          className={`content-area ${isMetadataView ? "metadata-view" : isQueryView ? "query-view" : isDiscoveryView ? "discovery-view" : ""}`}
          aria-label={isMetadataView ? "Snowflake metadata workspace" : isQueryView ? "Snowflake query workspace" : isDiscoveryView ? "Schema discovery workspace" : "Snowflake connection workspace"}
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
                  <span role="columnheader" />
                  <span role="columnheader">Name</span>
                  <span role="columnheader">Type</span>
                  <span role="columnheader">Descriptions</span>
                </div>
                {tables.map((table) => {
                  const isSelected = selectedTable?.name === table.name;
                  return (
                    <div
                      className={`table-row${isSelected ? " is-selected" : ""}`}
                      role="row"
                      key={`${table.database}.${table.schema}.${table.name}`}
                      onClick={() => setSelectedTable(isSelected ? null : table)}
                      style={{ cursor: "pointer" }}
                    >
                      <span role="cell" className="table-checkbox-cell">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => setSelectedTable(isSelected ? null : table)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Select ${table.name}`}
                        />
                      </span>
                      <span role="cell">{table.name}</span>
                      <span role="cell">{table.type}</span>
                      <span role="cell" className={`quality quality-${table.descriptionStatus}`}>
                        {table.descriptionStatus}
                      </span>
                    </div>
                  );
                })}
                {tables.length === 0 ? (
                  <div className="empty-state">
                    {tableState === "loading" ? "Loading tables" : "No table list run yet"}
                  </div>
                ) : null}
              </div>

              {tableState === "ready" && (
                <button
                  className="metadata-action"
                  type="button"
                  onClick={() => selectedTable && void selectTableMetadata(selectedTable)}
                  disabled={!selectedTable || metadataState === "loading"}
                  title={selectedTable ? `Load metadata for ${selectedTable.name}` : "Select a table to load its metadata"}
                >
                  {metadataState === "loading" ? "Loading metadata…" : selectedTable ? `Load Metadata: ${selectedTable.name}` : "Select a table"}
                </button>
              )}
            </div>

            {isMetadataView ? (
              <div className="panel metadata-panel">
                  <div className="panel-heading metadata-heading">
                    <div>
                      <h2>Metadata</h2>
                      <p>
                        {selectedMetadata
                          ? `${selectedMetadata.database}.${selectedMetadata.schema}.${selectedMetadata.table}`
                          : "Selected table"}
                      </p>
                    </div>
                    <div className="metadata-actions">
                      <button
                        className="metadata-secondary-action"
                        type="button"
                        onClick={() => void suggestDescriptions()}
                        disabled={!selectedMetadata || suggestionState === "loading"}
                      >
                        {suggestionState === "loading" ? "Suggesting" : "Suggest"}
                      </button>
                      <button
                        className="metadata-save-action"
                        type="button"
                        onClick={() => void saveDescriptions()}
                        disabled={!selectedMetadata || saveState === "loading"}
                      >
                        {saveState === "loading" ? "Saving" : "Save"}
                      </button>
                    </div>
                  </div>

                  {metadataState === "loading" ? <div className="empty-state">Loading metadata</div> : null}

                  {metadataState !== "loading" && selectedMetadata ? (
                    <div className="metadata-list" role="table" aria-label="Selected table metadata">
                      <div className="metadata-row metadata-header" role="row">
                        <span role="columnheader">Field</span>
                        <span role="columnheader">Schema</span>
                        <span role="columnheader">Description</span>
                        <span role="columnheader">Quality</span>
                        <span role="columnheader">Score</span>
                        <span role="columnheader">Recommendation</span>
                      </div>
                      {selectedMetadata.columns.map((column) => {
                        const analysis = analysisByColumn[column.name.toUpperCase()];
                        return (
                          <div className="metadata-row" role="row" key={column.name}>
                            <span role="cell">{column.name}</span>
                            <span role="cell">
                              {column.dataType}
                              {column.nullable ? ` · ${column.nullable === "YES" ? "nullable" : "required"}` : ""}
                            </span>
                            <span role="cell">
                              <textarea
                                aria-label={`${column.name} description`}
                                value={editedDescriptions[column.name] ?? column.description}
                                onChange={(event) => updateEditedDescription(column.name, event.target.value)}
                                placeholder="No description"
                              />
                            </span>
                            <span role="cell">
                              {analysis ? (
                                <span className={`quality quality-${analysis.result.quality}`}>
                                  {analysis.result.quality}
                                </span>
                              ) : (
                                "-"
                              )}
                            </span>
                            <span role="cell">{analysis ? analysis.result.score : "-"}</span>
                            <span role="cell">
                              {analysis?.result.recommendation ?? analysis?.result.issues.join("; ") ?? "-"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  {metadataState !== "loading" && !selectedMetadata ? (
                    <div className="empty-state">Select metadata from a table</div>
                  ) : null}
              </div>
            ) : null}

            {isDiscoveryView ? (
              <div className="panel discovery-panel">
                <div className="panel-heading discovery-heading">
                  <div>
                    <h2>Schema Discovery</h2>
                    <p>
                      {discoveryResult
                        ? `${discoveryResult.database}.${discoveryResult.schema} · ${discoveryResult.table_count} tables`
                        : selectedDatabase && selectedSchema
                          ? `${selectedDatabase}.${selectedSchema}`
                          : "Select a schema to run"}
                    </p>
                  </div>
                  <button
                    className="metadata-save-action"
                    type="button"
                    onClick={() => void runDiscovery()}
                    disabled={!selectedWarehouse || !selectedDatabase || !selectedSchema || discoveryState === "loading"}
                  >
                    {discoveryState === "loading" ? "Running…" : "Run Discovery"}
                  </button>
                </div>

                {message && isDiscoveryView ? <p className="inline-error">{message}</p> : null}

                {discoveryState === "loading" ? (
                  <div className="empty-state">Fetching schema metadata and generating descriptions…</div>
                ) : discoveryResult ? (
                  <div className="discovery-body">
                    <div className="discovery-tables">
                      {discoveryResult.tables.map((table) => (
                        <div className="discovery-card" key={table.name}>
                          <div className="discovery-card-header">
                            <div className="discovery-card-title">
                              <span className="discovery-table-name">{table.name}</span>
                              <span className={`discovery-purpose purpose-${table.purpose}`}>
                                {table.purpose}
                              </span>
                            </div>
                            <div className="discovery-card-meta">
                              <span>{table.estimated_row_count.toLocaleString()} rows</span>
                              <span>{table.column_count} columns</span>
                              <span className="discovery-coverage-text">
                                {table.existing_description_coverage.percent}% described
                              </span>
                            </div>
                          </div>
                          {table.description ? (
                            <p className="discovery-description">{table.description}</p>
                          ) : null}
                          {table.key_columns.length > 0 ? (
                            <div className="discovery-key-columns">
                              {table.key_columns.map((col) => (
                                <span className="discovery-col-chip" key={col}>{col}</span>
                              ))}
                            </div>
                          ) : null}
                          <div className="discovery-coverage-bar">
                            <div
                              className="discovery-coverage-fill"
                              style={{ width: `${table.existing_description_coverage.percent}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {discoveryResult.relationships.length > 0 ? (
                      <div className="discovery-section">
                        <h3 className="discovery-section-title">Detected Relationships</h3>
                        <div className="discovery-relationships">
                          {discoveryResult.relationships.map((rel, i) => (
                            <div className="discovery-rel-row" key={i}>
                              <span className="discovery-rel-from">{rel.from_table}</span>
                              <span className="discovery-rel-col">.{rel.from_column}</span>
                              <span className="discovery-rel-arrow">→</span>
                              <span className="discovery-rel-to">{rel.to_table}</span>
                              <span className="discovery-rel-type">{rel.relationship}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {discoveryResult.summary_stats.length > 0 ? (
                      <div className="discovery-section">
                        <h3 className="discovery-section-title">Sampled Statistics</h3>
                        <div className="discovery-stats-list">
                          {discoveryResult.summary_stats.map((s) => (
                            <div className="discovery-stats-card" key={s.table}>
                              <div className="discovery-stats-header">
                                <span className="discovery-stats-name">{s.table}</span>
                                <span className="discovery-stats-meta">
                                  {s.sampled_row_count != null
                                    ? `~${Math.round(s.sampled_row_count / (s.sample_percent / 100)).toLocaleString()} est. rows`
                                    : `${s.estimated_row_count.toLocaleString()} est. rows`}
                                </span>
                              </div>
                              {Object.keys(s.stats).length > 0 ? (
                                <dl className="discovery-stats-dl">
                                  {Object.entries(s.stats).map(([key, val]) => (
                                    <div key={key}>
                                      <dt>{key.replace(/_/g, " ")}</dt>
                                      <dd>{val != null ? String(val) : "—"}</dd>
                                    </div>
                                  ))}
                                </dl>
                              ) : (
                                <p className="discovery-stats-empty">No numeric or date columns sampled.</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="empty-state">
                    Select a warehouse, database, and schema, then click Run Discovery.
                  </div>
                )}
              </div>
            ) : null}

            {isQueryView ? (
              <div className="panel query-panel">
                <div className="panel-heading query-heading">
                  <div>
                    <h2>Query</h2>
                    <p>
                      {selectedMetadata
                        ? `${selectedMetadata.database}.${selectedMetadata.schema}.${selectedMetadata.table}`
                        : "No table selected"}
                    </p>
                  </div>
                  <button
                    className="metadata-save-action"
                    type="button"
                    onClick={() => void runQuery()}
                    disabled={!selectedMetadata || queryState === "loading"}
                  >
                    {queryState === "loading" ? "Running" : "Run Query"}
                  </button>
                </div>

                <div className="query-workspace">
                  <label className="query-label">
                    <span>Question</span>
                    <textarea
                      value={queryText}
                      onChange={(event) => setQueryText(event.target.value)}
                      placeholder="Ask a question about the selected table"
                    />
                  </label>

                  {queryResult ? (
                    <div className="query-result">
                      <div className="query-sql">
                        <p>Generated SQL</p>
                        <pre>{queryResult.sql}</pre>
                      </div>
                      <div className="query-explanation">
                        <p>{queryResult.explanation || "Query executed."}</p>
                        <span>{queryResult.rowCount} rows returned</span>
                      </div>
                      <div className="query-table" role="table" aria-label="Query results">
                        <div className="query-row query-header" role="row">
                          {queryResult.columns.map((column) => (
                            <span role="columnheader" key={column}>
                              {column}
                            </span>
                          ))}
                        </div>
                        {queryResult.rows.map((row, rowIndex) => (
                          <div className="query-row" role="row" key={`query-row-${rowIndex}`}>
                            {queryResult.columns.map((column) => (
                              <span role="cell" key={`${rowIndex}-${column}`}>
                                {formatQueryValue(row[column])}
                              </span>
                            ))}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="empty-state">
                      {queryState === "loading"
                        ? "Generating SQL and querying Snowflake"
                        : selectedMetadata
                          ? "No query run yet"
                          : "Load metadata from the Metadata tab first"}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
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

function descriptionsByColumnName(metadata: TableMetadata): Record<string, string> {
  return Object.fromEntries(metadata.columns.map((column) => [column.name, column.description]));
}

function metadataWithEditedDescriptions(
  metadata: TableMetadata,
  descriptions: Record<string, string>,
): TableMetadata {
  return {
    ...metadata,
    columns: metadata.columns.map((column) => ({
      ...column,
      description: descriptions[column.name] ?? column.description,
    })),
  };
}

function buildAnalysisByColumnName(
  analysis: MetadataDescriptionAnalysis | null,
): Record<string, DescriptionAnalysisColumn> {
  if (!analysis) {
    return {};
  }
  return Object.fromEntries(
    analysis.tables.flatMap((table) =>
      table.columns.map((column) => [column.column_name.toUpperCase(), column]),
    ),
  );
}

function formatQueryValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}
