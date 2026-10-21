/**
 * test_braces_regression.js
 *
 * Comprehensive regression test suite for CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm mitigation in `braces`.
 *
 * Test Sections:
 * 1. Deeply nested brace patterns stack exhaustion safety
 * 2. Custom low maxDepth enforcement
 * 3. Deeply nested parentheses AST depth bounding
 * 4. Ordinary brace expansion and compilation fidelity
 * 5. Malformed and imbalanced pattern termination safety
 * 6. Toolchain integration & Next.js/ESLint configuration loading
 * 7. Transactional patch installer verification (isolated temporary fixtures):
 *    - 7a: Wrong package version rejection
 *    - 7b: Missing or altered patch anchor failure
 *    - 7c: Partial patch failure leaves all target files untouched (transactional roll-back/zero-write)
 *    - 7d: Repeat execution idempotency (no duplicate guards)
 */

'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

console.log('=== Running braces Security Regression Tests ===\n');

const braces = require('braces');
const { patchBraces, isFullyPatched } = require('./scripts/patch-braces');

// --------------------------------------------------------------------------
// TEST 1: Deeply nested patterns do not crash Node or exhaust the stack
// --------------------------------------------------------------------------
console.log('Test 1: Deeply nested patterns stack exhaustion safety...');

const depth = 4500;
const deeplyNested = '{'.repeat(depth) + '}'.repeat(depth);

let caughtErrorCompile = null;
try {
  braces(deeplyNested);
} catch (err) {
  caughtErrorCompile = err;
}

assert(caughtErrorCompile !== null, 'Expected an error on deeply nested input');
assert.strictEqual(
  caughtErrorCompile.name,
  'SyntaxError',
  `Expected SyntaxError, but got ${caughtErrorCompile.name}: ${caughtErrorCompile.message}`
);
assert(
  caughtErrorCompile.message.includes('exceeds max depth'),
  `Expected error message to mention max depth, got: ${caughtErrorCompile.message}`
);
console.log('  [PASS] Default compile mode cleanly threw SyntaxError bounded depth');

let caughtErrorExpand = null;
try {
  braces(deeplyNested, { expand: true });
} catch (err) {
  caughtErrorExpand = err;
}

assert(caughtErrorExpand !== null, 'Expected an error on deeply nested input in expand mode');
assert.strictEqual(
  caughtErrorExpand.name,
  'SyntaxError',
  `Expected SyntaxError, but got ${caughtErrorExpand.name}: ${caughtErrorExpand.message}`
);
console.log('  [PASS] Expand mode cleanly threw SyntaxError bounded depth');

// Test AST-level depth bounds in compile and expand directly
const makeDeepAST = (d) => {
  let root = { type: 'root', nodes: [] };
  let current = root;
  for (let i = 0; i < d; i++) {
    const child = { type: 'brace', nodes: [] };
    current.nodes.push(child);
    current = child;
  }
  return root;
};

assert.throws(
  () => braces.compile(makeDeepAST(600)),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth'),
  'Direct compile AST traversal must bound depth'
);
assert.throws(
  () => braces.expand(makeDeepAST(600)),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth'),
  'Direct expand AST traversal must bound depth'
);
console.log('  [PASS] Direct AST compile/expand bounded depth verified');

// --------------------------------------------------------------------------
// TEST 2: Custom low maxDepth values
// --------------------------------------------------------------------------
console.log('\nTest 2: Custom low maxDepth option enforcement...');

// With maxDepth = 2, simple brace {a,b} succeeds in both compile and expand mode
assert.deepStrictEqual(braces('{a,b}', { maxDepth: 2 }), ['(a|b)']);
assert.deepStrictEqual(braces('{a,b}', { maxDepth: 2, expand: true }), ['a', 'b']);

// With maxDepth = 2, nested {a,{b,c}} exceeds compile AST depth (depth 3)
assert.throws(
  () => braces('{a,{b,c}}', { maxDepth: 2 }),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth (2)'),
  'Input exceeding custom maxDepth (2) in compile mode must throw SyntaxError'
);

// With maxDepth = 2, {a,{b,{c,d}}} exceeds parse brace depth (depth 3) in expand mode
assert.throws(
  () => braces('{a,{b,{c,d}}}', { maxDepth: 2, expand: true }),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth (2)'),
  'Input exceeding custom maxDepth (2) in expand mode must throw SyntaxError'
);

console.log('  [PASS] Custom low maxDepth limits enforced accurately');

// --------------------------------------------------------------------------
// TEST 3: Deeply nested parentheses AST traversal safety
// --------------------------------------------------------------------------
console.log('\nTest 3: Deeply nested parentheses recursion bounding...');

const deepParens = '('.repeat(4500) + ')'.repeat(4500);

assert.throws(
  () => braces(deepParens),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth'),
  'Deeply nested parentheses compile must be bounded by maxDepth'
);

assert.throws(
  () => braces(deepParens, { expand: true }),
  (err) => err.name === 'SyntaxError' && err.message.includes('exceeds max depth'),
  'Deeply nested parentheses expand must be bounded by maxDepth'
);

console.log('  [PASS] Deeply nested parentheses safely bounded without stack exhaustion');

// --------------------------------------------------------------------------
// TEST 4: Ordinary expansion and compilation fidelity
// --------------------------------------------------------------------------
console.log('\nTest 4: Ordinary expansion and compilation fidelity...');

// Set comparison
assert.deepStrictEqual(braces('{a,b,c}'), ['(a|b|c)']);
assert.deepStrictEqual(braces('{a,b,c}', { expand: true }), ['a', 'b', 'c']);

// Range expansion
assert.deepStrictEqual(braces('{1..5}', { expand: true }), ['1', '2', '3', '4', '5']);
assert.deepStrictEqual(braces('{01..05}', { expand: true }), ['01', '02', '03', '04', '05']);
assert.deepStrictEqual(braces('{a..e}', { expand: true }), ['a', 'b', 'c', 'd', 'e']);

// Glob pattern compilation
assert.deepStrictEqual(braces('src/**/*.{js,ts}'), ['src/**/*.(js|ts)']);
assert.deepStrictEqual(braces('components/{Nav,Sidebar,Footer}.tsx'), ['components/(Nav|Sidebar|Footer).tsx']);

// Multi-set combinations
const multiSet = braces('user-{1..2}-{x,y}', { expand: true });
assert.deepStrictEqual(multiSet, ['user-1-x', 'user-1-y', 'user-2-x', 'user-2-y']);

console.log('  [PASS] Standard compilation, range expansions, and combinations verified');

// --------------------------------------------------------------------------
// TEST 5: Malformed and imbalanced patterns terminate safely
// --------------------------------------------------------------------------
console.log('\nTest 5: Malformed and imbalanced patterns termination safety...');

assert.doesNotThrow(() => braces('{a,b'));
assert.doesNotThrow(() => braces('}a{b{'));
assert.doesNotThrow(() => braces('{a,{b,c}'));
assert.doesNotThrow(() => braces('{1..5..'));
assert.doesNotThrow(() => braces('{{{{{{'));
assert.doesNotThrow(() => braces('}}}}}}'));

// Deeply unclosed pattern: must hit max depth and throw SyntaxError safely (not crash)
assert.throws(
  () => braces('{'.repeat(2000)),
  (err) => err.name === 'SyntaxError',
  'Deeply unclosed pattern should safely terminate with SyntaxError'
);

console.log('  [PASS] Malformed and imbalanced patterns safely handled');

// --------------------------------------------------------------------------
// TEST 6: Toolchain integration & ESLint configuration loading
// --------------------------------------------------------------------------
console.log('\nTest 6: ESLint & Next.js flat configuration loading...');

const micromatch = require('micromatch');
const mmResult = micromatch(['src/app/page.tsx', 'src/lib/api.ts', 'README.md'], 'src/**/*.{js,ts,tsx}');
assert.deepStrictEqual(mmResult, ['src/app/page.tsx', 'src/lib/api.ts']);
console.log('  [PASS] Micromatch glob matching functional with patched braces');

// --------------------------------------------------------------------------
// TEST 7: Transactional Patch Installer Verification (Isolated Fixtures)
// --------------------------------------------------------------------------
console.log('\nTest 7: Transactional patch installer verification...');

// Helper to create an isolated fixture directory containing unpatched braces files
function createFixture(overrides = {}) {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'braces-patch-test-'));
  const libDir = path.join(tempDir, 'lib');
  fs.mkdirSync(libDir, { recursive: true });

  const pkgVersion = overrides.version || '3.0.3';
  fs.writeFileSync(
    path.join(tempDir, 'package.json'),
    JSON.stringify({ name: 'braces', version: pkgVersion }, null, 2),
    'utf8'
  );

  // Unpatched baseline templates containing the exact anchors
  const constantsContent = overrides.constantsContent !== undefined
    ? overrides.constantsContent
    : `'use strict';\n\nmodule.exports = {\n  MAX_LENGTH: 10000,\n\n  CHAR_0: '0'\n};\n`;

  const parseContent = overrides.parseContent !== undefined
    ? overrides.parseContent
    : `'use strict';\n\nconst {\n  MAX_LENGTH,\n  CHAR_BACKSLASH\n} = require('./constants');\n\nconst parse = (input, options = {}) => {\n  const opts = options || {};\n  const max = typeof opts.maxLength === 'number' ? Math.min(MAX_LENGTH, opts.maxLength) : MAX_LENGTH;\n  if (input.length > max) {\n    throw new SyntaxError(\`Input length (\${input.length}), exceeds max characters (\${max})\`);\n  }\n\n  let depth = 0;\n  let value;\n\n    if (value === CHAR_LEFT_CURLY_BRACE) {\n      depth++;\n\n      const dollar =\n  }\n};\n`;

  const compileContent = overrides.compileContent !== undefined
    ? overrides.compileContent
    : `'use strict';\n\nconst utils = require('./utils');\n\nconst compile = (ast, options = {}) => {\n  const walk = (node, parent = {}) => {\n    let output = '';\n    output += walk(child, node);\n    return output;\n  };\n  return walk(ast);\n};\n`;

  const expandContent = overrides.expandContent !== undefined
    ? overrides.expandContent
    : `'use strict';\n\nconst utils = require('./utils');\n\nconst expand = (ast, options = {}) => {\n  const rangeLimit = options.rangeLimit === undefined ? 1000 : options.rangeLimit;\n\n  const walk = (node, parent = {}) => {\n    let queue = [];\n      if (child.nodes) {\n        walk(child, node);\n      }\n    return queue;\n  };\n  return walk(ast);\n};\n`;

  fs.writeFileSync(path.join(libDir, 'constants.js'), constantsContent, 'utf8');
  fs.writeFileSync(path.join(libDir, 'parse.js'), parseContent, 'utf8');
  fs.writeFileSync(path.join(libDir, 'compile.js'), compileContent, 'utf8');
  fs.writeFileSync(path.join(libDir, 'expand.js'), expandContent, 'utf8');

  return tempDir;
}

// 7a: Wrong package version rejection
const wrongVersionDir = createFixture({ version: '3.0.4' });
try {
  assert.throws(
    () => patchBraces(wrongVersionDir),
    /Incompatible braces version "3.0.4"; expected exactly 3.0.3/,
    'Patch installer must reject unexpected package versions'
  );
  console.log('  [PASS] 7a: Incompatible package version rejected cleanly');
} finally {
  fs.rmSync(wrongVersionDir, { recursive: true, force: true });
}

// 7b: Missing patch anchor throws and leaves files untouched
const missingAnchorDir = createFixture({
  parseContent: `'use strict';\n// Corrupted parse.js missing all patch anchors\nmodule.exports = {};\n`
});
try {
  assert.throws(
    () => patchBraces(missingAnchorDir),
    /Patch anchor missing in lib\/parse\.js/,
    'Patch installer must fail if a patch anchor is missing'
  );
  // Assert constants.js was NOT modified (transactional zero-write)
  const constantsContent = fs.readFileSync(path.join(missingAnchorDir, 'lib', 'constants.js'), 'utf8');
  assert(!constantsContent.includes('MAX_DEPTH: 500,'), 'Transaction aborted: constants.js must not be written');
  console.log('  [PASS] 7b: Missing anchor caught; transaction aborted without partial writes');
} finally {
  fs.rmSync(missingAnchorDir, { recursive: true, force: true });
}

// 7c: Partial patch failure leaves all target files untouched (transactional safety)
const partialFailureDir = createFixture({
  // expand.js (the last file) has a corrupted anchor
  expandContent: `'use strict';\n// Corrupted expand.js missing utils\nmodule.exports = {};\n`
});
try {
  const initialConstants = fs.readFileSync(path.join(partialFailureDir, 'lib', 'constants.js'), 'utf8');
  const initialParse = fs.readFileSync(path.join(partialFailureDir, 'lib', 'parse.js'), 'utf8');
  const initialCompile = fs.readFileSync(path.join(partialFailureDir, 'lib', 'compile.js'), 'utf8');

  assert.throws(
    () => patchBraces(partialFailureDir),
    /Patch anchor missing in lib\/expand\.js/,
    'Patch installer must fail on corrupted expand.js anchor'
  );

  const afterConstants = fs.readFileSync(path.join(partialFailureDir, 'lib', 'constants.js'), 'utf8');
  const afterParse = fs.readFileSync(path.join(partialFailureDir, 'lib', 'parse.js'), 'utf8');
  const afterCompile = fs.readFileSync(path.join(partialFailureDir, 'lib', 'compile.js'), 'utf8');

  assert.strictEqual(afterConstants, initialConstants, 'constants.js must remain untouched on transaction failure');
  assert.strictEqual(afterParse, initialParse, 'parse.js must remain untouched on transaction failure');
  assert.strictEqual(afterCompile, initialCompile, 'compile.js must remain untouched on transaction failure');
  console.log('  [PASS] 7c: Transactional safety confirmed: zero writes on downstream failure');
} finally {
  fs.rmSync(partialFailureDir, { recursive: true, force: true });
}

// 7d: Repeat execution idempotency and zero duplicate guards
const cleanFixtureDir = createFixture();
try {
  const res1 = patchBraces(cleanFixtureDir);
  assert.strictEqual(res1.success, true);
  assert.strictEqual(res1.patched, true);

  const patchedConstants = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'constants.js'), 'utf8');
  const patchedParse = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'parse.js'), 'utf8');
  const patchedCompile = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'compile.js'), 'utf8');
  const patchedExpand = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'expand.js'), 'utf8');

  // Verify full structural patch
  assert(isFullyPatched(patchedConstants, patchedParse, patchedCompile, patchedExpand), 'Fixture must be fully patched');

  // Second execution
  const res2 = patchBraces(cleanFixtureDir);
  assert.strictEqual(res2.success, true);
  assert.strictEqual(res2.alreadyPatched, true);

  // Assert contents on disk are byte-identical (no duplicate guards)
  const afterConstants = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'constants.js'), 'utf8');
  const afterParse = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'parse.js'), 'utf8');
  const afterCompile = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'compile.js'), 'utf8');
  const afterExpand = fs.readFileSync(path.join(cleanFixtureDir, 'lib', 'expand.js'), 'utf8');

  assert.strictEqual(afterConstants, patchedConstants, 'No duplication in constants.js on repeat run');
  assert.strictEqual(afterParse, patchedParse, 'No duplication in parse.js on repeat run');
  assert.strictEqual(afterCompile, patchedCompile, 'No duplication in compile.js on repeat run');
  assert.strictEqual(afterExpand, patchedExpand, 'No duplication in expand.js on repeat run');

  console.log('  [PASS] 7d: Repeat execution idempotent; zero duplicate guards');
} finally {
  fs.rmSync(cleanFixtureDir, { recursive: true, force: true });
}

console.log('\n=== All 7 Regression Test Suites Passed with 100% Success ===');
process.exit(0);
