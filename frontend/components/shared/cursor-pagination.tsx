"use client";

import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface CursorPaginationProps {
  hasMore: boolean;
  isLoading: boolean;
  onLoadMore: () => void;
}

export function CursorPagination({ hasMore, isLoading, onLoadMore }: CursorPaginationProps) {
  if (!hasMore) return null;

  return (
    <div className="flex justify-center pt-4">
      <Button variant="outline" onClick={onLoadMore} disabled={isLoading}>
        {isLoading ? (
          <>
            <Loader2 className="animate-spin" />
            Loading...
          </>
        ) : (
          "Load More"
        )}
      </Button>
    </div>
  );
}
