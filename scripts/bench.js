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

// === NEW HELPER FUNCTION TO SIMULATE FILE CHANGE ===
function simulateChange(configPath) {
    const configDir = join(configPath, '..'); // Directory containing tsconfig.json
    
    let tsFileToModify = null;
    
    // Attempt to find the first non-test .ts or .tsx file in the config directory or 'src' subdirectory
    const searchDirs = [configDir, join(configDir, 'src')];

    for (const searchDir of searchDirs) {
        if (!existsSync(searchDir)) continue;
        try {
            const files = readdirSync(searchDir, { withFileTypes: true });
            for (const file of files) {
                if (file.isFile() && (file.name.endsWith(".ts") || file.name.endsWith(".tsx")) && !file.name.includes(".test.") && !file.name.endsWith(".d.ts")) {
                    tsFileToModify = join(searchDir, file.name);
                    break;
                }
            }
            if (tsFileToModify) break;
        } catch {
            // ignore directory read error
        }
    }

    if (tsFileToModify) {
        // Append a harmless comment to force a timestamp change/recompile
        writeFileSync(tsFileToModify, `\n// Incremental Test Comment ${Date.now()}\n`, { flag: 'a' });
        return basename(tsFileToModify);
    }
    return null; // No suitable file found
}
// === END NEW HELPER FUNCTION ===

// === MODIFIED PARSING FUNCTION ===
function parseTscOutput(text) {
  const grab = (k) => {
    const m = text && text.match(new RegExp(`${k}\\s*:\\s*([0-9.,]+)`));
    return m ? Number(m[1].replace(/,/g, "")) : null;
  };

  // Existing metrics
  const extracted = { 
    files: grab("Files"), 
    lines: grab("Lines"), 
    memoryKB: grab("Memory used"), 
    totalTimeSec: grab("Total time") 
  };

  // 1. Phase Times (Typing Domination)
  const phaseBlockMatch = text && text.match(/Time:\s*([\s\S]*?)\n/);
  if (phaseBlockMatch) {
    const block = phaseBlockMatch[1]; 
    const parserMatch = block.match(/([\d\.]+)s parser/);
    const checkerMatch = block.match(/([\d\.]+)s checker/);
    const emitterMatch = block.match(/([\d\.]+)s emitter/);

    if (parserMatch) extracted.parsingTimeSec = parseFloat(parserMatch[1]);
    if (checkerMatch) extracted.typeCheckingTimeSec = parseFloat(checkerMatch[1]);
    if (emitterMatch) extracted.emitTimeSec = parseFloat(emitterMatch[1]);
  }

  // 2. Diagnostic Counts (Minor Correlation)
  const errorMatch = text && text.match(/Found (\d+) error/i);
  if (errorMatch) {
    extracted.diagnosticCount = parseInt(errorMatch[1], 10);
  } else {
    const summaryMatch = text && text.match(/(\d+)\s*errors,\s*(\d+)\s*warnings/i);
    if (summaryMatch) {
        extracted.diagnosticCount = parseInt(summaryMatch[1], 10) + parseInt(summaryMatch[2], 10);
    } else {
        extracted.diagnosticCount = 0; 
    }
  }

  return extracted;
}
// === END MODIFIED PARSING FUNCTION ===

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
    results.push({ project: name, target: null, exitCode: 2, wallMs: 0, files: null, lines: null, memoryKB: null, totalTimeSec: null, log: null, parsingTimeSec: null, typeCheckingTimeSec: null, emitTimeSec: null, diagnosticCount: null, buildType: "skip" });
    continue;
  }
  
  // === MODIFIED LOOP FOR INCREMENTAL BUILD TESTING ===
  for (const cfg of tsconfigs) {
    // 1. Full Build (Build Type: 'full')
    const label_full = `${name}__${basename(join(cfg, "..")) || "root"}`;
    console.log(`=== ${label_full}: FULL BUILD ===`);
    
    // Add --incremental to the command to ensure tsbuildinfo is generated
    const t0_full = Date.now();
    const res_full = run("npx", ["--yes", "-p", "typescript@latest", "tsc", "--noEmit", "--pretty", "false", "--diagnostics", "--skipLibCheck", "true", "--incremental", "-p", cfg], dir, { NODE_OPTIONS: "--max-old-space-size=8192" });
    const t1_full = Date.now();
    const logFile_full = `logs/${label_full}-full-tsc.log`;
    writeFileSync(join(ROOT, logFile_full), (res_full.stdout || "") + (res_full.stderr || ""));
    const diag_full = parseTscOutput((res_full.stdout || "") + (res_full.stderr || ""));
    
    results.push({ project: name, target: cfg.replace(dir + "/", ""), exitCode: res_full.status, wallMs: t1_full - t0_full, ...diag_full, log: logFile_full, buildType: "full" });
    
    // --- Simulate Change ---
    const modifiedFile = simulateChange(cfg);
    if (!modifiedFile) {
        console.warn(`Could not find a source file to modify for incremental test in ${label_full}. Skipping incremental run.`);
        continue;
    }
    console.log(`--- Simulated change in ${modifiedFile} ---`);
    
    // 2. Incremental Build (Build Type: 'inc')
    console.log(`=== ${label_full}: INCREMENTAL BUILD ===`);
    // Re-run the exact same command, relying on the generated .tsbuildinfo
    const t0_inc = Date.now();
    const res_inc = run("npx", ["--yes", "-p", "typescript@latest", "tsc", "--noEmit", "--pretty", "false", "--diagnostics", "--skipLibCheck", "true", "--incremental", "-p", cfg], dir, { NODE_OPTIONS: "--max-old-space-size=8192" });
    const t1_inc = Date.now();
    const logFile_inc = `logs/${label_full}-inc-tsc.log`;
    writeFileSync(join(ROOT, logFile_inc), (res_inc.stdout || "") + (res_inc.stderr || ""));
    const diag_inc = parseTscOutput((res_inc.stdout || "") + (res_inc.stderr || ""));

    results.push({ project: name, target: cfg.replace(dir + "/", ""), exitCode: res_inc.status, wallMs: t1_inc - t0_inc, ...diag_inc, log: logFile_inc, buildType: "inc" });
  }
}

writeFileSync(join(LOGS_DIR, "tsc-summary.json"), JSON.stringify(results, null, 2));
console.log("\nWrote logs/tsc-summary.json");