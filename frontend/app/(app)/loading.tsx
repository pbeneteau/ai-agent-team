export default function AppLoading() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-48 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)]" />
      <div className="h-4 w-96 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-bg-tertiary)]" />
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-[var(--radius-lg)] bg-[var(--color-bg-tertiary)]"
          />
        ))}
      </div>
    </div>
  );
}
