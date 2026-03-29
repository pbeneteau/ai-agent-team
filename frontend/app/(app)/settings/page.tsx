"use client";

/**
 * Settings index — redirects to first settings tab.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/settings/workspace"); }, [router]);
  return null;
}
