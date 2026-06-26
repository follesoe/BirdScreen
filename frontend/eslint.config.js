import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import noUnsanitized from 'eslint-plugin-no-unsanitized'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Strict from the start (greenfield): type-aware rules and a11y/i18n are errors,
// not warnings. No grandfather opt-outs.
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      noUnsanitized.configs.recommended,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    settings: { react: { version: 'detect' } },
    plugins: { react },
    rules: {
      'max-lines': ['error', { max: 1500, skipBlankLines: true, skipComments: true }],
      'max-lines-per-function': ['error', { max: 250, skipBlankLines: true, skipComments: true }],
      // i18n: no hardcoded UI strings — every visible string goes through
      // useTranslation() so the UI can be translated later (English default).
      'react/jsx-no-literals': [
        'error',
        {
          noStrings: true,
          ignoreProps: true,
          allowedStrings: [
            '.', ',', ':', ';', '!', '?', '—', '–', '-', '|', '/', '·',
            '%', '+', '×', '(', ')', '[', ']', '…', '✓', '✗', '°', '°C',
          ],
        },
      ],
    },
  },
])
