import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ListPagesResponse, PageRecord } from "../api/types";

export function ProjectReviewQueuePage() {
  const { projectId = "" } = useParams();
  const queue = useQuery({
    queryKey: ["review-queue", projectId],
    queryFn: () =>
      api.get<ListPagesResponse>(
        `/api/data/projects/${projectId}/pages?review_needed=true&limit=500`,
      ),
  });

  if (queue.isLoading) return <p className="text-slate-500">Loading…</p>;
  if (!queue.data) return <p className="text-red-600">Project not found.</p>;

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Review queue</h1>
          <p className="text-xs text-slate-500">
            {queue.data.total} pages need review
          </p>
        </div>
        <Link
          to={`/projects/${projectId}`}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          ← Back to project
        </Link>
      </header>

      {queue.data.pages.length === 0 ? (
        <p className="rounded border border-dashed border-slate-300 bg-white p-6 text-center text-slate-500">
          Nothing to review — every page is complete.
        </p>
      ) : (
        <ul className="divide-y rounded border bg-white">
          {queue.data.pages.map((p: PageRecord) => (
            <li key={p.idx0}>
              <Link
                to={`/projects/${projectId}/pages/${p.idx0}/review`}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div className="flex items-center gap-3">
                  {p.thumbnail_key && (
                    <img
                      src={`/cdn/${p.thumbnail_key}`}
                      alt=""
                      className="h-12 w-8 rounded object-cover"
                      loading="lazy"
                    />
                  )}
                  <div>
                    <div className="font-mono text-sm">
                      {p.prefix || `#${p.idx0}`}
                    </div>
                    <div className="text-xs text-slate-500">
                      status: {p.processing_status}
                      {p.processing_error && (
                        <span className="ml-2 text-rose-600">
                          {p.processing_error}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <span className="text-slate-400">→</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
