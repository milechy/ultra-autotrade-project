// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/lib/useLanguage.ts
// liff-chat 専用の言語切替 Context。
// - localStorage "lang" ("ja"|"en") を正本とし、cookie "NEXT_LOCALE" に同期書込する。
// - SSR hydration safe: 初期値は "ja" 固定、mount 後に localStorage を反映する。
// - React Context 経由で lang state を全体共有する（hook を別々に2回呼ぶと state 分裂）。
"use client"

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react"

export type Language = "ja" | "en"

const LANG_LS_KEY = "lang"
const LANG_COOKIE = "NEXT_LOCALE"

interface LanguageContextValue {
  language: Language
  setLanguage: (lang: Language) => void
}

const LanguageContext = createContext<LanguageContextValue>({
  language: "ja",
  setLanguage: () => {},
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  // SSR safe: 初期値 "ja" 固定、mount 後 localStorage を反映
  const [language, setLanguageState] = useState<Language>("ja")

  useEffect(() => {
    if (typeof window === "undefined") return
    const saved = localStorage.getItem(LANG_LS_KEY)
    if (saved === "ja" || saved === "en") {
      setLanguageState(saved)
    }
  }, [])

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang)
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(LANG_LS_KEY, lang)
      } catch {
        // quota 超過などは無視
      }
      // cookie "NEXT_LOCALE" に同期書込（middleware が x-locale ヘッダーに変換する）
      document.cookie = `${LANG_COOKIE}=${lang};path=/;max-age=31536000;SameSite=Lax`
    }
  }, [])

  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext)
}
