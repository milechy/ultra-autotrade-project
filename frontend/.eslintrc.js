/** @type {import('eslint').Linter.Config} */
module.exports = {
  extends: ['next/core-web-vitals'],
  rules: {
    // Rule 1: recharts を直接 import 禁止（SSR クラッシュ防止）
    // 違反時は *Recharts.tsx / *Chart.tsx に分離して dynamic import する
    'no-restricted-imports': [
      'error',
      {
        paths: [
          {
            name: 'recharts',
            message:
              "recharts は SSR でクラッシュします。別ファイルに分離して dynamic(() => import('./XxxRecharts'), { ssr: false }) で読み込んでください。",
          },
        ],
      },
    ],

    // Rule 2: useState(Math.random()) は SSR hydration mismatch を起こす
    // Rule 4: useEffect 内の直接 fetch は認証漏れのリスクがある（warn）
    'no-restricted-syntax': [
      'warn',
      {
        selector:
          "CallExpression[callee.name='useState'] CallExpression[callee.object.name='Math'][callee.property.name='random']",
        message:
          'useState(Math.random()) は SSR hydration mismatch を起こします。useEffect 内で setState してください。',
      },
      {
        selector:
          "CallExpression[callee.name='useEffect'] CallExpression[callee.name='fetch']",
        message:
          'useEffect 内の直接 fetch は認証漏れのリスクがあります。useAuthFetch Hook の使用を検討してください。',
      },
    ],
  },
  overrides: [
    // Rule 1 exception: *Recharts*.tsx / *Chart*.tsx は dynamic import 先なので許可
    {
      files: ['**/*Recharts*.tsx', '**/*Chart*.tsx', '**/charts/**/*.tsx'],
      rules: {
        'no-restricted-imports': 'off',
      },
    },
    // Rule 3: root layout に WagmiProvider を配置しない（admin ルートでクラッシュ防止）
    {
      files: ['**/app/layout.tsx'],
      rules: {
        'no-restricted-syntax': [
          'error',
          {
            selector: "JSXIdentifier[name='WagmiProvider']",
            message:
              'WagmiProvider は root layout に置かないでください。(user) route group の layout にスコープしてください。',
          },
          {
            selector:
              "CallExpression[callee.name='useState'] CallExpression[callee.object.name='Math'][callee.property.name='random']",
            message:
              'useState(Math.random()) は SSR hydration mismatch を起こします。useEffect 内で setState してください。',
          },
          {
            selector:
              "CallExpression[callee.name='useEffect'] CallExpression[callee.name='fetch']",
            message:
              'useEffect 内の直接 fetch は認証漏れのリスクがあります。useAuthFetch Hook の使用を検討してください。',
          },
        ],
      },
    },
    // Rule 3 exception: wallet ライブラリは WagmiProvider を定義する側なので許可
    {
      files: ['**/lib/wallet/**/*.tsx', '**/lib/wallet/**/*.ts'],
      rules: {
        'no-restricted-syntax': 'off',
      },
    },
  ],
}
