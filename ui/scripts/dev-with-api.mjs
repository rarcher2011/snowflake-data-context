import { spawn } from "node:child_process";

const repoRoot = new URL("../..", import.meta.url);
const uiRoot = new URL("..", import.meta.url);
const apiHealthUrl = "http://127.0.0.1:8000/openapi.json";
const requiredApiPaths = ["/api/snowflake/databases", "/api/snowflake/table-metadata"];
const children = [];
let shuttingDown = false;

const api = spawnProcess("api", "uv", [
  "run",
  "--no-sync",
  "python",
  "-m",
  "openai_snowflake_agent_context.ui_backend",
], repoRoot);

children.push(api);

try {
  await waitForApi();
  children.push(spawnProcess("ui", "vite", ["--host", "127.0.0.1"], uiRoot));
} catch (error) {
  process.stderr.write(`[api] ${error instanceof Error ? error.message : String(error)}\n`);
  shutdown(1);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

function spawnProcess(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    env: {
      ...process.env,
      UV_CACHE_DIR: ".uv-cache",
    },
    shell: true,
    stdio: "pipe",
  });

  child.stdout.on("data", (data) => {
    process.stdout.write(prefixLines(name, data));
  });
  child.stderr.on("data", (data) => {
    process.stderr.write(prefixLines(name, data));
  });
  child.on("exit", (code) => {
    if (code && !shuttingDown) {
      shutdown(code);
    }
  });

  return child;
}

async function waitForApi() {
  const timeoutMs = 60000;
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(apiHealthUrl);
      if (response.ok) {
        const openApi = await response.json();
        const missingPaths = requiredApiPaths.filter((path) => !openApi.paths?.[path]);
        if (missingPaths.length === 0) {
          return;
        }
        throw new Error(
          `API at ${apiHealthUrl} is missing ${missingPaths.join(", ")}. ` +
            "Stop the old backend process on port 8000 and rerun npm run dev.",
        );
      }
    } catch (error) {
      if (
        error instanceof Error &&
        requiredApiPaths.some((path) => error.message.includes(path))
      ) {
        throw error;
      }
      // The API process is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${apiHealthUrl}`);
}

function shutdown(code) {
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      child.kill();
    }
  }
  process.exit(code);
}

function prefixLines(name, data) {
  return data
    .toString()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => `[${name}] ${line}\n`)
    .join("");
}
