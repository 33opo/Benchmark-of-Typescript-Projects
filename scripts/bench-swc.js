const { execSync, spawnSync } = require("child_process");
const { readdirSync, writeFileSync, existsSync, statSync } = require("fs");
const { join } = require("path");

const ROOT = process.cwd();
const PROJECTS_DIR = join(ROOT, "projects");
const LOGS_DIR = join(ROOT, "logs");

// Utility function to get the size of a directory recursively
function getDirectorySize(dir) {
    if (!existsSync(dir)) return 0;
    try {
        // Use 'du -sk' (disk usage in kilobytes) which is available in the Docker image
        const output = execSync(`du -sk ${dir} | cut -f1`, { encoding: 'utf8' });
        // du -sk returns KB, convert to a number
        return parseInt(output.trim(), 10);
    } catch (e) {
        console.warn(`Could not determine size of ${dir}: ${e.message}`);
        return 0;
    }
}

const entries = readdirSync(PROJECTS_DIR).filter(n => {
    try { return statSync(join(PROJECTS_DIR, n)).isDirectory(); } catch { return false; }
});

const results = [];
for (const name of entries) {
    const dir = join(PROJECTS_DIR, name);
    const label = `${name}__swc`;
    console.log(`\n=== ${name}: swc benchmark ===`);
    
    // 1. Find all TS/TSX files to use as entry points
    // We exclude node_modules, dist, and build directories.
    let tsFiles = [];
    try {
        // Use 'find' command for efficient file search (available in Docker image)
        const findOutput = execSync(
            `find . -type f \\( -name "*.ts" -o -name "*.tsx" \\) -not -path "./node_modules/*" -not -path "./dist/*" -not -path "./build/*"`, 
            { cwd: dir, encoding: "utf8" }
        );
        tsFiles = findOutput.split('\n').filter(Boolean);
    } catch (e) {
        console.warn(`File finding failed for ${name}: ${e.message}`);
    }

    if (tsFiles.length === 0) {
        console.log(`No .ts/.tsx files found for ${name}, skipping.`);
        results.push({ project: name, tool: "swc", exitCode: 2, wallMs: 0, outputSizeKB: 0, log: "No source files found." });
        continue;
    }
    
    const OUT_DIR = 'out_swc';
    
    // 2. Execute SWC Transpilation
    const t0 = Date.now();
    let exitCode = 0;
    let log = '';
    
    try {
        // SWC command:
        // -p @swc/cli@latest: ensures the latest CLI is used
        // swc: the main command
        // . : specifies the current directory (project root) as the input
        // --out-dir: specifies the output directory
        // --source-maps: includes source maps (important for production equivalence)
        // --quiet: suppresses most standard output
        const swc_command = `npx --yes -p @swc/cli@latest swc . --out-dir=${OUT_DIR} --source-maps --extensions .ts,.tsx --quiet`;
        
        // Use spawnSync to execute the command and capture output/status
        const swc_res = spawnSync("bash", ["-c", swc_command], { cwd: dir, encoding: 'utf8', stdio: 'pipe' });
        
        exitCode = swc_res.status || 0;
        log = (swc_res.stdout || "") + (swc_res.stderr || "");

        if (exitCode !== 0) {
            throw new Error(`SWC failed with exit code ${exitCode}.`);
        }
        
    } catch (e) {
        // SWC throws on failure (e.g., config error, syntax error)
        exitCode = 1;
        log += `\nError running SWC: ${e.message}`;
        console.warn(`SWC failed for ${name}: ${e.message.split('\n')[0]}`);
    }
    const t1 = Date.now();
    
    // 3. Calculate Output Size
    const outputSizeKB = getDirectorySize(join(dir, OUT_DIR));

    // 4. Clean up output directory (optional but recommended for fresh runs)
    try { execSync(`rm -rf ${OUT_DIR}`, { cwd: dir, stdio: 'ignore' }); } catch {}

    // 5. Store Results
    const logFile = `logs/${label}-swc.log`;
    writeFileSync(join(ROOT, logFile), log);

    results.push({ 
        project: name, 
        tool: "swc", 
        exitCode: exitCode, 
        wallMs: t1 - t0, 
        outputSizeKB: outputSizeKB,
        log: logFile 
    });
}

writeFileSync(join(LOGS_DIR, "swc-summary.json"), JSON.stringify(results, null, 2));
console.log("\nWrote logs/swc-summary.json");