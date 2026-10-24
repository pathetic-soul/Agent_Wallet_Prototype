import fs from "node:fs";
import path from "node:path";
import solc from "solc";

const root = process.cwd();
const sourceRoot = path.join(root, "contracts", "src");
const outputRoot = path.join(root, "out");

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(absolute) : [absolute];
  });
}

const sources = Object.fromEntries(
  walk(sourceRoot)
    .filter((file) => file.endsWith(".sol"))
    .map((file) => [
      path.relative(root, file).replaceAll(path.sep, "/"),
      { content: fs.readFileSync(file, "utf8") },
    ]),
);

function resolveImport(importPath) {
  const candidates = [
    path.join(root, importPath),
    path.join(root, "node_modules", importPath),
    path.join(sourceRoot, importPath),
  ];
  const match = candidates.find((candidate) => fs.existsSync(candidate));
  return match
    ? { contents: fs.readFileSync(match, "utf8") }
    : { error: `Import not found: ${importPath}` };
}

const input = {
  language: "Solidity",
  sources,
  settings: {
    optimizer: { enabled: true, runs: 200 },
    evmVersion: "cancun",
    outputSelection: {
      "*": { "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"] },
    },
  },
};

const output = JSON.parse(solc.compile(JSON.stringify(input), { import: resolveImport }));
const diagnostics = output.errors ?? [];
for (const diagnostic of diagnostics) {
  const stream = diagnostic.severity === "error" ? process.stderr : process.stdout;
  stream.write(`${diagnostic.formattedMessage}\n`);
}
if (diagnostics.some((diagnostic) => diagnostic.severity === "error")) {
  process.exit(1);
}

fs.rmSync(outputRoot, { recursive: true, force: true });
for (const [sourceName, contracts] of Object.entries(output.contracts ?? {})) {
  if (!sourceName.startsWith("contracts/src/")) continue;
  for (const [contractName, artifact] of Object.entries(contracts)) {
    const directory = path.join(outputRoot, `${contractName}.sol`);
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(
      path.join(directory, `${contractName}.json`),
      JSON.stringify({ contractName, sourceName, ...artifact }, null, 2),
    );
  }
}

console.log(`Compiled ${Object.keys(sources).length} project sources with solc ${solc.version()}`);

