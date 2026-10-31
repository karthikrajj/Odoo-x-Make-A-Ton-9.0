const browserGlobals = Object.fromEntries(
  [
    'document',
    'window',
    'location',
    'history',
    'URLSearchParams',
    'Intl',
    'setTimeout',
    'clearTimeout',
    'fetch',
    'FormData',
    'performance',
  ].map((name) => [name, 'readonly']),
);
const nodeGlobals = Object.fromEntries(
  [
    'require',
    'module',
    'process',
    'Buffer',
    'console',
    'URLSearchParams',
    'Intl',
    'setTimeout',
    'clearTimeout',
    'performance',
    'fetch',
  ].map((name) => [name, 'readonly']),
);
const rules = {
  'no-undef': 'error',
  'no-unused-vars': ['error', { args: 'after-used', argsIgnorePattern: '^_' }],
  'no-dupe-args': 'error',
  'no-dupe-keys': 'error',
  'no-unreachable': 'error',
  'valid-typeof': 'error',
  'no-constant-condition': 'error',
  'no-fallthrough': 'error',
};
export default [
  { ignores: ['dist/**', 'backups/**', 'reports/**'] },
  {
    files: ['static/**/*.js'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'script', globals: browserGlobals },
    rules,
  },
  {
    files: ['tests/**/*.cjs'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'commonjs', globals: nodeGlobals },
    rules,
  },
];
