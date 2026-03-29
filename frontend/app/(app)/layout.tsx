import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/top-bar";

/**
 * App layout — sidebar navigation + top bar + main content area.
 *
 * Ref: TDD-05 Section 3.2, Section 18 (responsive)
 * Sidebar hidden below md, shown as icon-only at md, full at lg.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden md:block">
        <Sidebar />
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main id="main-content" className="flex-1 overflow-y-auto p-4 sm:p-6" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}
