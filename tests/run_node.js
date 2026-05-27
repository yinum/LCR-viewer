// Headless runner for HTML test pages (ladder_labeler_test.html, uploader_test.html, …).
//
// The HTML test pages assume a browser (uses document.getElementById, prompt,
// etc.). This runner shims just enough of the DOM + window to let them execute
// under Node, so subagents and CI can verify pure-math + state tests without a
// browser.
//
// Usage:  node tests/run_node.js [test-page-filename]
//   Default filename: ladder_labeler_test.html
// Exit:   0 on all-pass; 1 on any failure or load error.
//
// What it shims:
//   - document.getElementById('summary') / 'log'  → fake elements
//     whose .textContent and .className we read at the end for the summary line.
//   - document.createElement('pre') → fake element with .className and
//     .textContent properties; appendChild collects them into a buffer.
//   - window.prompt → stubbed per-test (the test file overrides window.prompt
//     temporarily); the default impl throws (no test should silently prompt).
//
// What it does NOT shim: Plotly, layout, IndexedDB, FileSystem APIs. The
// test files use none of these — they test pure functions and state.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const here = path.dirname(__filename);
const testFile = process.argv[2] || 'ladder_labeler_test.html';
const testHtml = fs.readFileSync(path.join(here, testFile), 'utf8');

// Find which JS module(s) the test page loads via <script src="../X.js">.
// Concatenate them all, then extract the inline test script.
const srcRefs = [...testHtml.matchAll(
  /<script src="\.\.\/([^"]+\.js)"><\/script>/g
)].map(m => m[1]);
let moduleSrc = '';
for (const ref of srcRefs) {
  moduleSrc += fs.readFileSync(path.join(here, '..', ref), 'utf8') + '\n';
}
const inlineMatch = testHtml.match(/<\/script>\s*<script>([\s\S]*?)<\/script>/);
if (!inlineMatch) {
  console.error(`Could not extract inline test script from ${testFile}`);
  process.exit(1);
}
const inlineScript = inlineMatch[1];

// Fake DOM elements: collect appended children for the summary readout.
function makeFakeEl(tag) {
  return {
    tagName: tag,
    className: '',
    textContent: '',
    children: [],
    appendChild(c) { this.children.push(c); },
  };
}
const summary = makeFakeEl('div');
const log = makeFakeEl('div');

const fakeDoc = {
  getElementById(id) {
    if (id === 'summary') return summary;
    if (id === 'log') return log;
    return null;
  },
  createElement(tag) { return makeFakeEl(tag); },
};

const fakeWindow = {
  prompt: () => { throw new Error('window.prompt called without a stub'); },
};

// Build a sandbox and run the module(s) + the inline test script.
const sandbox = {
  document: fakeDoc,
  window: fakeWindow,
  console,
  // Map a top-level `window.prompt = …` assignment in test code to fakeWindow.
  // (vm scripts see top-level `window` as an alias for our sandbox's window.)
  Math, Number, JSON, Array, Set, Map, Date, Symbol, Infinity, NaN,
};
sandbox.global = sandbox;

// Make global prompt delegate to window.prompt (in browsers they're the same).
// When test code does window.prompt = ..., the global prompt must also change.
Object.defineProperty(sandbox, 'prompt', {
  get() { return fakeWindow.prompt; },
  set(fn) { fakeWindow.prompt = fn; },
  configurable: true,
});

vm.createContext(sandbox);

try {
  vm.runInContext(moduleSrc, sandbox, { filename: 'modules' });
} catch (e) {
  console.error('Load error in modules:', e.message);
  process.exit(1);
}

try {
  vm.runInContext(inlineScript, sandbox, { filename: testFile + ' (inline)' });
} catch (e) {
  // The inline script has its own try/catch around the test body, so reaching
  // this branch means the wrapper itself threw — usually a missing shim.
  console.error('Uncaught error running test script:', e.message);
  process.exit(1);
}

// Replay the log for visibility (one line per check).
for (const c of log.children) {
  console.log(c.textContent);
}
console.log('---');
console.log(summary.textContent);
process.exit(summary.textContent.includes(' 0 failed.') ? 0 : 1);
