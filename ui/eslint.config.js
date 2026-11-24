import js from '@eslint/js'
import i18next from 'eslint-plugin-i18next'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'src/api/schema.d.ts'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // UI copy goes through the catalogs (src/i18n/locales): a literal in JSX text or in an
    // attribute people see or hear is an error. The attributes listed are never copy. An
    // intended literal (a brand, a name, an example in the content's language) gets
    // `// eslint-disable-next-line i18next/no-literal-string -- <why>`.
    files: ['src/**/*.tsx'],
    ignores: ['**/*.test.tsx', 'src/test/**', 'src/components/ui/**'],
    plugins: { i18next },
    rules: {
      'i18next/no-literal-string': [
        'error',
        {
          mode: 'jsx-only',
          'jsx-attributes': {
            exclude: [
              'className',
              'style',
              'type',
              'key',
              'id',
              'width',
              'height',
              'value',
              'htmlFor',
              'autoComplete',
              'to',
              'href',
              'role',
              'variant',
              'size',
              'side',
              'edge',
              'align',
              'as',
              'i18nKey',
              'dateTime',
              'data-.*',
              'aria-orientation',
              'aria-haspopup',
              'aria-current',
              'aria-live',
              'inputMode',
              'accept',
              'rel',
              'target',
              'lang',
              'name',
            ],
          },
        },
      ],
    },
  },
  {
    // Test helpers, and shadcn/ui files that export variants next to components.
    files: ['src/test/**', '**/*.test.{ts,tsx}', 'src/components/ui/**'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
  {
    // Tests assert an element exists before using it; `!` there is not a hidden bug.
    files: ['**/*.test.{ts,tsx}'],
    rules: { '@typescript-eslint/no-non-null-assertion': 'off' },
  },
  {
    files: ['**/*.{js,mjs}'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  {
    // Served as is and run by the browser before the app (index.html).
    files: ['public/**/*.js'],
    languageOptions: { globals: globals.browser, sourceType: 'script' },
  },
)
