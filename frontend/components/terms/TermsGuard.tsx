// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useEffect, useState } from "react";
import TermsModal from "./TermsModal";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function TermsGuard({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [needsAcceptance, setNeedsAcceptance] = useState(false);

  useEffect(() => {
    const checkTerms = async () => {
      const token = localStorage.getItem("ultra_auth_token") ?? "";
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/auth/terms/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setNeedsAcceptance(data.needs_acceptance);
        }
      } catch {
        // check失敗時はブロックしない
      } finally {
        setLoading(false);
      }
    };
    checkTerms();
  }, []);

  if (loading) return null;

  if (needsAcceptance) {
    return <TermsModal onAccepted={() => setNeedsAcceptance(false)} />;
  }

  return <>{children}</>;
}
