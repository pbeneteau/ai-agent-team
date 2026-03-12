"use client";

import { Bot, Sparkles } from "lucide-react";

import type { PlanForm } from "@/components/chat/plan-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

interface PlanFormCardProps {
  form: PlanForm;
  values: Record<string, string>;
  phase: "idle" | "form" | "review" | "revising" | "executing" | "failed" | "cancelled" | "completed";
  onChange: (fieldId: string, value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export function PlanFormCard({
  form,
  values,
  phase,
  onChange,
  onCancel,
  onSubmit,
}: PlanFormCardProps) {
  const missingRequiredFields = form.fields.filter(
    (field) => field.required && !values[field.id]?.trim(),
  );
  const isSubmitDisabled = phase !== "form" || missingRequiredFields.length > 0;

  return (
    <Card className="mx-auto max-w-3xl gap-4 bg-background/95 shadow-sm ring-foreground/8">
      <CardHeader className="gap-3 border-b border-border/60">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Bot className="size-4" />
          </div>

          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">{form.title}</CardTitle>
              <Badge variant="outline" className="border-border/70 bg-background text-muted-foreground">
                Guided form
              </Badge>
            </div>
            {form.description ? (
              <p className="text-sm leading-6 text-muted-foreground">{form.description}</p>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {form.fields.map((field) => (
          <div key={field.id} className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-medium text-foreground">
              <label htmlFor={field.id}>{field.label}</label>
              {field.required ? (
                <Badge variant="secondary" className="bg-amber-100 text-amber-800">
                  Required
                </Badge>
              ) : null}
            </div>

            {field.type === "select" && field.options?.length ? (
              <select
                id={field.id}
                className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50"
                value={values[field.id] || ""}
                onChange={(event) => onChange(field.id, event.target.value)}
                disabled={phase !== "form"}
              >
                <option value="">Choose…</option>
                {field.options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : field.type === "textarea" ? (
              <Textarea
                id={field.id}
                rows={4}
                placeholder={field.placeholder}
                value={values[field.id] || ""}
                onChange={(event) => onChange(field.id, event.target.value)}
                disabled={phase !== "form"}
                className="min-h-[108px] rounded-2xl bg-background"
              />
            ) : (
              <Input
                id={field.id}
                type="text"
                placeholder={field.placeholder}
                value={values[field.id] || ""}
                onChange={(event) => onChange(field.id, event.target.value)}
                disabled={phase !== "form"}
                className="h-10 rounded-xl bg-background"
              />
            )}

            {field.required && !values[field.id]?.trim() ? (
              <p className="text-xs text-amber-700">This field is required to continue.</p>
            ) : null}
          </div>
        ))}

        {missingRequiredFields.length > 0 ? (
          <div className="flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <Sparkles className="size-3.5" />
            Fill in every required field before sending the form.
          </div>
        ) : null}
      </CardContent>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border/60 bg-muted/20 px-4 py-3">
        <Button variant="ghost" onClick={onCancel} disabled={phase !== "form"}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={isSubmitDisabled}>
          Submit
        </Button>
      </div>
    </Card>
  );
}
