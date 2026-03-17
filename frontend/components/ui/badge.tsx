import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border px-2 py-0 text-[11px] font-medium tracking-[0.01em] whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "border-primary bg-primary text-primary-foreground [a]:hover:bg-primary/90",
        secondary:
          "border-[var(--ops-border)] bg-[var(--ops-surface-muted)] text-[var(--ops-ink)] [a]:hover:bg-[var(--ops-control-hover)]",
        destructive:
          "border-[var(--ops-signal-danger-border)] bg-[var(--ops-signal-danger-bg)] text-[var(--ops-signal-danger-ink)] focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline:
          "border-[var(--ops-border)] bg-[var(--ops-surface-elevated)] text-[var(--ops-muted-ink)] [a]:hover:bg-[var(--ops-control-hover)] [a]:hover:text-[var(--ops-ink)]",
        ghost:
          "border-transparent bg-transparent hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "border-transparent bg-transparent text-primary underline-offset-4 hover:underline",
        info:
          "border-[var(--ops-signal-info-border)] bg-[var(--ops-signal-info-bg)] text-[var(--ops-signal-info-ink)]",
        positive:
          "border-[var(--ops-signal-positive-border)] bg-[var(--ops-signal-positive-bg)] text-[var(--ops-signal-positive-ink)]",
        warning:
          "border-[var(--ops-signal-warning-border)] bg-[var(--ops-signal-warning-bg)] text-[var(--ops-signal-warning-ink)]",
        danger:
          "border-[var(--ops-signal-danger-border)] bg-[var(--ops-signal-danger-bg)] text-[var(--ops-signal-danger-ink)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
