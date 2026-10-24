import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import process from 'node:process';

const virtualEnvironmentPython = process.platform === 'win32'
  ? '.venv/Scripts/python.exe'
  : '.venv/bin/python';
const executable = process.env.AGENT_WALLET_PYTHON
  || (existsSync(virtualEnvironmentPython) ? virtualEnvironmentPython : process.platform === 'win32' ? 'py' : 'python3');

const child = spawn(executable, process.argv.slice(2), { stdio: 'inherit' });

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}

child.on('error', (error) => {
  console.error(`Unable to start ${executable}: ${error.message}`);
  process.exitCode = 1;
});

child.on('exit', (code, signal) => {
  process.exitCode = signal ? 1 : (code ?? 1);
});
