import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">Page not found</h1>
      <p className="text-sm text-[var(--color-text-secondary)]">
        The page you are looking for does not exist.
      </p>
      <Link
        href="/projects"
        className="rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-[var(--color-text-inverse)] hover:bg-[var(--color-accent-hover)] transition-colors"
      >
        Go to Projects
      </Link>
    </div>
  );
}
