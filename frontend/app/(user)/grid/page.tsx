'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// This route is a duplicate of /user/grid (see frontend/app/user/grid/page.tsx), which is the
// live, nav-linked page (frontend/components/user/UserHeader.tsx adminNavItems links here via
// href="/user/grid"). No in-app link points at /grid, so this page only exists as a redirect
// target for anyone with a stale bookmark/link to /grid.
// Kept (not deleted) per URL-cleanup policy; the original implementation lives on unused in
// this route's history.
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { LoadingPage } from "@/components/shared/LoadingSpinner";

export default function GridRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/user/grid");
  }, [router]);

  return <LoadingPage />;
}
