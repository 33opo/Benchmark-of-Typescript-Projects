const { spawnSync, execSync } = require("child_process");
const { readdirSync, writeFileSync, existsSync, mkdirSync, statSync } = require("fs");
const { join, basename } = require("path");

const ROOT = process.cwd();
const PROJECTS_DIR = join(ROOT, "projects");
const LOGS_DIR = join(ROOT, "logs");
if (!existsSync(LOGS_DIR)) mkdirSync(LOGS_DIR, { recursive: true });

function run(cmd, args, cwd, extraEnv = {}) {
  return spawnSync(cmd, args, { cwd, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, env: { ...process.env, ...extraEnv } });
}

function installDeps(dir) {
  if (existsSync(join(dir, "pnpm-lock.yaml"))) {
    try { execSync("pnpm -v", { stdio: "ignore" }); } catch { execSync("corepack prepare pnpm@latest --activate", { stdio: "inherit" }); }
    execSync("pnpm install --ignore-scripts", { cwd: dir, stdio: "inherit" });
    return;
  }
  if (existsSync(join(dir, "yarn.lock"))) {
    try { execSync("yarn -v", { stdio: "ignore" }); } catch { execSync("corepack prepare yarn@stable --activate", { stdio: "inherit" }); }
    execSync("yarn install --ignore-scripts", { cwd: dir, stdio: "inherit" });
    return;
  }
  if (existsSync(join(dir, "package-lock.json"))) {
    try { execSync("npm ci --ignore-scripts", { cwd: dir, stdio: "inherit" }); return; } catch {}
  }
  execSync("npm install --ignore-scripts", { cwd: dir, stdio: "inherit" });
}

function findTsconfigsRecursive(dir, depth = 0, maxDepth = 4, out = []) {
  const deny = new Set(["node_modules", ".git", "dist", "build", "coverage", ".next", "out"]);
  if (depth > maxDepth) return out;
  const f = join(dir, "tsconfig.json");
  try { if (statSync(f).isFile()) out.push(f); } catch {}
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    if (deny.has(e.name)) continue;
    findTsconfigsRecursive(join(dir, e.name), depth + 1, maxDepth, out);
  }
  return Array.from(new Set(out));
}

function parseDiag(text) {
  const grab = (k) => {
    const m = text && text.match(new RegExp(`${k}\\s*:\\s*([0-9.,]+)`));
    return m ? Number(m[1].replace(/,/g, "")) : null;
  };
  return { files: grab("Files"), lines: grab("Lines"), memoryKB: grab("Memory used"), totalTimeSec: grab("Total time") };
}

const entries = readdirSync(PROJECTS_DIR).filter(n => {
  try { return statSync(join(PROJECTS_DIR, n)).isDirectory(); } catch { return false; }
});

const results = [];
for (const name of entries) {
  const dir = join(PROJECTS_DIR, name);
  console.log(`\n=== ${name}: install ===`);
  try { installDeps(dir); } catch (e) { console.warn(`Install failed for ${name}: ${e.message}`); }
  const tsconfigs = findTsconfigsRecursive(dir);
  if (tsconfigs.length === 0) {
    console.log(`=== ${name}: no tsconfig.json found, skipping ===`);
    results.push({ project: name, target: null, exitCode: 2, wallMs: 0, files: null, lines: null, memoryKB: null, totalTimeSec: null, log: null });
    continue;
  }
  for (const cfg of tsconfigs) {
    const label = `${name}__${basename(join(cfg, "..")) || "root"}`;
    console.log(`=== ${name}: tsc -p ${cfg} ===`);
    const t0 = Date.now();
    const res = run("npx", ["--yes", "-p", "typescript@latest", "tsc", "--noEmit", "--pretty", "false", "--diagnostics", "--skipLibCheck", "true", "-p", cfg], dir, { NODE_OPTIONS: "--max-old-space-size=8192" });
    const t1 = Date.now();
    const logFile = `logs/${label}-tsc.log`;
    writeFileSync(join(ROOT, logFile), (res.stdout || "") + (res.stderr || ""));
    const diag = parseDiag((res.stdout || "") + (res.stderr || ""));
    results.push({ project: name, target: cfg.replace(dir + "/", ""), exitCode: res.status, wallMs: t1 - t0, ...diag, log: logFile });
  }
}

writeFileSync(join(LOGS_DIR, "tsc-summary.json"), JSON.stringify(results, null, 2));
console.log("\nWrote logs/tsc-summary.json");
