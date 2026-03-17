"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import {
  getDomainSecondaryNav,
  isProductNavItemActive,
  type ProductDomainId,
} from "@/lib/config/product-navigation";
import { cn } from "@/lib/utils";

interface DomainSecondaryNavProps {
  domain: ProductDomainId;
  className?: string;
}

export function DomainSecondaryNav({ domain, className }: DomainSecondaryNavProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const items = getDomainSecondaryNav(domain);

  if (items.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex flex-wrap gap-1.5 rounded-[18px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] p-1.5",
        className,
      )}
    >
      {items.map((item) => {
        const isActive = isProductNavItemActive(item, pathname, searchParams);

        return (
          <Link
            key={item.id}
            href={item.href}
            className={cn(
              "min-w-[120px] rounded-[14px] border px-3 py-2.5 transition-colors",
              isActive
                ? "border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] text-[var(--ops-ink)]"
                : "border-transparent text-[var(--ops-muted-ink)] hover:border-[var(--ops-border-soft)] hover:bg-[var(--ops-control-hover)] hover:text-[var(--ops-ink)]",
            )}
          >
            <p className="text-sm font-semibold">{item.label}</p>
            <p className="mt-1 text-[11px] leading-5 text-current/72">{item.description}</p>
          </Link>
        );
      })}
    </div>
  );
}
