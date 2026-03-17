"use client"

import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-[12px] border bg-clip-padding text-sm font-medium whitespace-nowrap transition-colors outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground shadow-[0_8px_20px_-18px_rgba(15,23,42,0.35)] hover:bg-primary/92",
        outline:
          "border-[var(--ops-control-border)] bg-[var(--ops-surface-elevated)] text-[var(--ops-ink)] hover:bg-[var(--ops-control-hover)] hover:text-[var(--ops-ink)] aria-expanded:bg-[var(--ops-control-hover)] aria-expanded:text-[var(--ops-ink)]",
        secondary:
          "border-[var(--ops-border)] bg-[var(--ops-surface-muted)] text-[var(--ops-ink)] hover:bg-[var(--ops-control-hover)] aria-expanded:bg-[var(--ops-control-hover)] aria-expanded:text-[var(--ops-ink)]",
        ghost:
          "border-transparent bg-transparent text-[var(--ops-muted-ink)] hover:bg-[var(--ops-control-hover)] hover:text-[var(--ops-ink)] aria-expanded:bg-[var(--ops-control-hover)] aria-expanded:text-[var(--ops-ink)] dark:hover:bg-muted/50",
        destructive:
          "border-[var(--ops-signal-danger-border)] bg-[var(--ops-signal-danger-bg)] text-[var(--ops-signal-danger-ink)] hover:bg-[#f8e0e0] focus-visible:border-destructive/40 focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:hover:bg-destructive/30 dark:focus-visible:ring-destructive/40",
        link: "border-transparent bg-transparent text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-3 has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        xs: "h-6 gap-1 rounded-[10px] px-2 text-xs in-data-[slot=button-group]:rounded-[10px] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[10px] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-[10px] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-3.5 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[10px] in-data-[slot=button-group]:rounded-[10px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[10px] in-data-[slot=button-group]:rounded-[10px]",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
