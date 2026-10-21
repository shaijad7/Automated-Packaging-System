/**
 * patch-braces.js
 *
 * Hardened, transactional local patch installer for transitive `braces` dependency.
 * Mitigates CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm (CWE-674 recursion stack exhaustion)
 * based on upstream PR #72 by bounding recursive AST depth to MAX_DEPTH = 500.
 *
 * Runs automatically via npm "postinstall" script.
 */

/* eslint-disable @typescript-eslint/no-require-imports */
'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Strict replacement helper:
 * - Throws if target anchor is missing
 * - Throws if target anchor appears more than once (ambiguity guard)
 * - Transparently handles CRLF and LF differences
 */
function strictReplace(content, target, replacement, fileLabel, patchLabel) {
  const isCRLF = content.includes('\r\n');
  const normalizedTarget = isCRLF ? target.replace(/\r?\n/g, '\r\n') : target.replace(/\r\n/g, '\n');
  const normalizedReplacement = isCRLF ? replacement.replace(/\r?\n/g, '\r\n') : replacement.replace(/\r\n/g, '\n');

  if (!content.includes(normalizedTarget)) {
    throw new Error(`[patch-braces] Patch anchor missing in ${fileLabel} for '${patchLabel}'`);
  }

  const occurrences = content.split(normalizedTarget).length - 1;
  if (occurrences !== 1) {
    throw new Error(
      `[patch-braces] Ambiguous anchor in ${fileLabel} for '${patchLabel}': expected exactly 1 occurrence, found ${occurrences}`
    );
  }

  return content.replace(normalizedTarget, normalizedReplacement);
}

/**
 * Validates the runtime guard structure across all four files.
 * Verifies actual AST traversal and depth limits, not merely a token string.
 */
function isFullyPatched(constants, parse, compile, expand) {
  const normalize = str => str.replace(/\r\n/g, '\n');
  const c = normalize(constants);
  const p = normalize(parse);
  const cmp = normalize(compile);
  const e = normalize(expand);

  const checks = [
    // 1. constants.js defines MAX_DEPTH
    c.includes('MAX_DEPTH: 500,'),

    // 2. parse.js imports MAX_DEPTH
    p.includes('MAX_DEPTH,\n  CHAR_BACKSLASH'),

    // 3. parse.js resolves maxDepth option
    p.includes("const maxDepth = typeof opts.maxDepth === 'number' ? Math.min(MAX_DEPTH, opts.maxDepth) : MAX_DEPTH;"),

    // 4. parse.js guards left curly brace depth
    p.includes('if (depth > maxDepth) {\n        throw new SyntaxError(`Input depth (${depth}), exceeds max depth (${maxDepth})`);\n      }'),

    // 5. compile.js imports MAX_DEPTH
    cmp.includes("const { MAX_DEPTH } = require('./constants');"),

    // 6. compile.js guards walk depth
    cmp.includes("const maxDepth = typeof options.maxDepth === 'number' ? Math.min(MAX_DEPTH, options.maxDepth) : MAX_DEPTH;\n\n  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > maxDepth) {\n      throw new SyntaxError(`Brace AST depth (${depth}) exceeds max depth (${maxDepth})`);\n    }"),

    // 7. compile.js increments child walk depth
    cmp.includes('output += walk(child, node, depth + 1);'),

    // 8. expand.js imports MAX_DEPTH
    e.includes("const { MAX_DEPTH } = require('./constants');"),

    // 9. expand.js guards walk depth
    e.includes("const maxDepth = typeof options.maxDepth === 'number' ? Math.min(MAX_DEPTH, options.maxDepth) : MAX_DEPTH;\n\n  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > maxDepth) {\n      throw new SyntaxError(`Brace AST depth (${depth}) exceeds max depth (${maxDepth})`);\n    }"),

    // 10. expand.js increments child walk depth
    e.includes('walk(child, node, depth + 1);')
  ];

  return checks.every(Boolean);
}

/**
 * Main patch routine.
 * Can be executed against standard node_modules or a temporary test fixture directory.
 */
function patchBraces(bracesDir = path.resolve(__dirname, '..', 'node_modules', 'braces')) {
  if (!fs.existsSync(bracesDir)) {
    console.log('[patch-braces] node_modules/braces directory not found, skipping patch.');
    return { success: true, skipped: true };
  }

  // 1. Version validation: require exactly 3.0.3
  const pkgPath = path.join(bracesDir, 'package.json');
  if (!fs.existsSync(pkgPath)) {
    throw new Error(`[patch-braces] Package manifest missing at ${pkgPath}`);
  }

  let pkg;
  try {
    pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  } catch (err) {
    throw new Error(`[patch-braces] Failed to parse package manifest at ${pkgPath}: ${err.message}`);
  }

  if (pkg.version !== '3.0.3') {
    throw new Error(`[patch-braces] Incompatible braces version "${pkg.version}"; expected exactly 3.0.3`);
  }

  // 2. Read all four target files into memory
  const constantsPath = path.join(bracesDir, 'lib', 'constants.js');
  const parsePath = path.join(bracesDir, 'lib', 'parse.js');
  const compilePath = path.join(bracesDir, 'lib', 'compile.js');
  const expandPath = path.join(bracesDir, 'lib', 'expand.js');

  for (const filePath of [constantsPath, parsePath, compilePath, expandPath]) {
    if (!fs.existsSync(filePath)) {
      throw new Error(`[patch-braces] Required target file missing: ${filePath}`);
    }
  }

  const constantsContent = fs.readFileSync(constantsPath, 'utf8');
  const parseContent = fs.readFileSync(parsePath, 'utf8');
  const compileContent = fs.readFileSync(compilePath, 'utf8');
  const expandContent = fs.readFileSync(expandPath, 'utf8');

  // 3. Idempotency & existing patch verification
  if (isFullyPatched(constantsContent, parseContent, compileContent, expandContent)) {
    console.log('[patch-braces] Target files are already verified and securely patched.');
    return { success: true, alreadyPatched: true };
  }

  // 4. In-memory preparation with strict replacement assertions
  const patchedConstants = strictReplace(
    constantsContent,
    'MAX_LENGTH: 10000,',
    'MAX_LENGTH: 10000,\n  MAX_DEPTH: 500,',
    'lib/constants.js',
    'MAX_DEPTH constant export'
  );

  let patchedParse = strictReplace(
    parseContent,
    '  MAX_LENGTH,',
    '  MAX_LENGTH,\n  MAX_DEPTH,',
    'lib/parse.js',
    'MAX_DEPTH import'
  );
  patchedParse = strictReplace(
    patchedParse,
    '  if (input.length > max) {\n    throw new SyntaxError(`Input length (${input.length}), exceeds max characters (${max})`);\n  }',
    '  if (input.length > max) {\n    throw new SyntaxError(`Input length (${input.length}), exceeds max characters (${max})`);\n  }\n\n  const maxDepth = typeof opts.maxDepth === \'number\' ? Math.min(MAX_DEPTH, opts.maxDepth) : MAX_DEPTH;',
    'lib/parse.js',
    'maxDepth option resolution'
  );
  patchedParse = strictReplace(
    patchedParse,
    '    if (value === CHAR_LEFT_CURLY_BRACE) {\n      depth++;\n\n      const dollar =',
    '    if (value === CHAR_LEFT_CURLY_BRACE) {\n      depth++;\n      if (depth > maxDepth) {\n        throw new SyntaxError(`Input depth (${depth}), exceeds max depth (${maxDepth})`);\n      }\n\n      const dollar =',
    'lib/parse.js',
    'parse curly brace depth guard'
  );

  let patchedCompile = strictReplace(
    compileContent,
    "const utils = require('./utils');",
    "const utils = require('./utils');\nconst { MAX_DEPTH } = require('./constants');",
    'lib/compile.js',
    'MAX_DEPTH import'
  );
  patchedCompile = strictReplace(
    patchedCompile,
    'const compile = (ast, options = {}) => {\n  const walk = (node, parent = {}) => {',
    'const compile = (ast, options = {}) => {\n  const maxDepth = typeof options.maxDepth === \'number\' ? Math.min(MAX_DEPTH, options.maxDepth) : MAX_DEPTH;\n\n  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > maxDepth) {\n      throw new SyntaxError(`Brace AST depth (${depth}) exceeds max depth (${maxDepth})`);\n    }',
    'lib/compile.js',
    'compile depth guard'
  );
  patchedCompile = strictReplace(
    patchedCompile,
    'output += walk(child, node);',
    'output += walk(child, node, depth + 1);',
    'lib/compile.js',
    'compile child walk depth increment'
  );

  let patchedExpand = strictReplace(
    expandContent,
    "const utils = require('./utils');",
    "const utils = require('./utils');\nconst { MAX_DEPTH } = require('./constants');",
    'lib/expand.js',
    'MAX_DEPTH import'
  );
  patchedExpand = strictReplace(
    patchedExpand,
    'const expand = (ast, options = {}) => {\n  const rangeLimit = options.rangeLimit === undefined ? 1000 : options.rangeLimit;\n\n  const walk = (node, parent = {}) => {',
    'const expand = (ast, options = {}) => {\n  const rangeLimit = options.rangeLimit === undefined ? 1000 : options.rangeLimit;\n  const maxDepth = typeof options.maxDepth === \'number\' ? Math.min(MAX_DEPTH, options.maxDepth) : MAX_DEPTH;\n\n  const walk = (node, parent = {}, depth = 0) => {\n    if (depth > maxDepth) {\n      throw new SyntaxError(`Brace AST depth (${depth}) exceeds max depth (${maxDepth})`);\n    }',
    'lib/expand.js',
    'expand depth guard'
  );
  patchedExpand = strictReplace(
    patchedExpand,
    '      if (child.nodes) {\n        walk(child, node);\n      }',
    '      if (child.nodes) {\n        walk(child, node, depth + 1);\n      }',
    'lib/expand.js',
    'expand child walk depth increment'
  );

  // 5. In-memory pre-write validation: ensure all guards are completely formed
  if (!isFullyPatched(patchedConstants, patchedParse, patchedCompile, patchedExpand)) {
    throw new Error('[patch-braces] Transaction aborted: In-memory patched code failed structural validation.');
  }

  // 6. Transactional disk writes: only reached if all 4 files are validated in memory
  fs.writeFileSync(constantsPath, patchedConstants, 'utf8');
  fs.writeFileSync(parsePath, patchedParse, 'utf8');
  fs.writeFileSync(compilePath, patchedCompile, 'utf8');
  fs.writeFileSync(expandPath, patchedExpand, 'utf8');

  // 7. Post-write verification from disk
  const vConstants = fs.readFileSync(constantsPath, 'utf8');
  const vParse = fs.readFileSync(parsePath, 'utf8');
  const vCompile = fs.readFileSync(compilePath, 'utf8');
  const vExpand = fs.readFileSync(expandPath, 'utf8');

  if (!isFullyPatched(vConstants, vParse, vCompile, vExpand)) {
    throw new Error('[patch-braces] Post-write verification failed: on-disk files do not match expected guards.');
  }

  console.log('[patch-braces] Successfully and transactionally applied security patch to braces@3.0.3.');
  return { success: true, patched: true };
}

if (require.main === module) {
  try {
    patchBraces();
  } catch (err) {
    console.error(err.message || err);
    process.exit(1);
  }
}

module.exports = { patchBraces, isFullyPatched, strictReplace };
