import { cn } from "@/lib/utils";

export interface SegmentedTabItem<T extends string> {
  id: T;
  label: string;
}

interface SegmentedTabsProps<T extends string> {
  items: SegmentedTabItem<T>[];
  value: T;
  onValueChange: (value: T) => void;
  className?: string;
}

export function SegmentedTabs<T extends string>({
  items,
  value,
  onValueChange,
  className,
}: SegmentedTabsProps<T>) {
  return (
    <div
      className={cn(
        "inline-flex flex-wrap gap-1 rounded-[16px] border border-[var(--ops-border)] bg-[var(--ops-surface-strong)] p-1",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onValueChange(item.id)}
            className={cn(
              "rounded-[12px] px-3 py-1.5 text-sm font-medium transition-colors",
              active
                ? "border border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] text-[var(--ops-ink)]"
                : "border border-transparent text-[var(--ops-muted-ink)] hover:bg-[var(--ops-control-hover)] hover:text-[var(--ops-ink)]",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
