"use client";

/**
 * Version switcher — tabs/buttons for navigating between artifact versions.
 *
 * Ref: TDD-05 Section 10.2
 */

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { VersionItem } from "@/lib/types/api";

interface VersionSwitcherProps {
  versions: VersionItem[];
  selectedVersion: number;
  onSelectVersion: (version: number) => void;
}

export function VersionSwitcher({ versions, selectedVersion, onSelectVersion }: VersionSwitcherProps) {
  if (versions.length <= 1) return null;

  return (
    <div className="flex items-center gap-1">
      <span className="mr-1 text-xs text-[var(--color-text-tertiary)]">Version:</span>
      {versions.map((v) => (
        <Button
          key={v.version_number}
          variant={v.version_number === selectedVersion ? "default" : "ghost"}
          size="xs"
          onClick={() => onSelectVersion(v.version_number)}
          className={cn(
            v.version_number === selectedVersion && "pointer-events-none",
          )}
        >
          v{v.version_number}
        </Button>
      ))}
    </div>
  );
}
