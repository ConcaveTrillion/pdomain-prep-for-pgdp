import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { PageRecord } from "../api/types";

interface OcrPageResponse {
  text: string;
  text_key: string;
  words: unknown[];
}

export function TextReviewPage() {
  const { projectId = "", idx0: idx0Str = "0" } = useParams();
  const idx0 = Number(idx0Str);
  const queryClient = useQueryClient();

  const [splitSuffix, setSplitSuffix] = useState<string>("");
  const [text, setText] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  const page = useQuery({
    queryKey: ["page", projectId, idx0],
    queryFn: () =>
      api.get<PageRecord>(`/api/data/projects/${projectId}/pages/${idx0}`),
  });

  const text$ = useQuery({
    enabled: !!page.data,
    queryKey: ["page-text", projectId, idx0, splitSuffix],
    queryFn: () =>
      api.get<{ text: string; text_key: string }>(
        `/api/data/projects/${projectId}/pages/${idx0}/text/${splitSuffix || "_"}`,
      ),
  });

  useEffect(() => {
    if (text$.data) {
      setText(text$.data.text);
      setDirty(false);
    } else if (text$.error) {
      // 404 = no text yet (probably needs OCR first)
      setText("");
      setDirty(false);
    }
  }, [text$.data, text$.error]);

  const save = useMutation({
    mutationFn: () =>
      api.patch<{ text_key: string }>(
        `/api/data/projects/${projectId}/pages/${idx0}/text`,
        { split_suffix: splitSuffix || null, text },
      ),
    onSuccess: () => {
      setDirty(false);
      queryClient.invalidateQueries({
        queryKey: ["page-text", projectId, idx0, splitSuffix],
      });
    },
  });

  const reocr = useMutation({
    mutationFn: () =>
      api.post<OcrPageResponse>("/api/gpu/run-ocr-page", {
        project_id: projectId,
        idx0,
        split_suffix: splitSuffix || null,
      }),
    onSuccess: (resp) => {
      setText(resp.text);
      setDirty(false);
      queryClient.invalidateQueries({
        queryKey: ["page-text", projectId, idx0, splitSuffix],
      });
    },
  });

  if (page.isLoading) return <p className="text-slate-500">Loading…</p>;
  if (!page.data) return <p className="text-red-600">Page not found.</p>;

  const splits = page.data.splits as Array<{ suffix: string; reading_order: number }>;

  return (
    <section className="space-y-3">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold">
            Text review — {page.data.prefix || `#${idx0}`}
          </h1>
          <p className="text-xs text-slate-500">{page.data.source_stem}</p>
        </div>
        <div className="flex items-center gap-2">
          {splits.length > 0 && (
            <select
              value={splitSuffix}
              onChange={(e) => setSplitSuffix(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">(whole page)</option>
              {[...splits]
                .sort((a, b) => a.reading_order - b.reading_order)
                .map((s) => (
                  <option key={s.suffix} value={s.suffix}>
                    {page.data!.prefix}
                    {s.suffix}
                  </option>
                ))}
            </select>
          )}
          <Link
            to={`/projects/${projectId}/pages/${Math.max(0, idx0 - 1)}/review`}
            className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"
          >
            ← Prev
          </Link>
          <Link
            to={`/projects/${projectId}/pages/${idx0 + 1}/review`}
            className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"
          >
            Next →
          </Link>
        </div>
      </header>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded border bg-white p-2">
          {page.data.processed_image_key ? (
            <img
              src={`/cdn/${page.data.processed_image_key}`}
              alt={page.data.prefix}
              className="max-h-[80vh] w-full object-contain"
            />
          ) : page.data.thumbnail_key ? (
            <img
              src={`/cdn/${page.data.thumbnail_key}`}
              alt={page.data.prefix}
              className="max-h-[80vh] w-full object-contain"
            />
          ) : (
            <div className="flex h-96 items-center justify-center text-slate-400">
              no image
            </div>
          )}
        </div>

        <div className="flex flex-col rounded border bg-white p-2">
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setDirty(true);
            }}
            spellCheck
            className="min-h-[60vh] w-full resize-y rounded border-0 p-2 font-mono text-sm focus:outline-none"
            placeholder={
              text$.error
                ? "No OCR text yet. Click 're-OCR' to run OCR for this page."
                : "Loading…"
            }
          />
          <div className="flex items-center gap-2 border-t pt-2">
            <button
              onClick={() => save.mutate()}
              disabled={!dirty || save.isPending}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50 hover:bg-slate-800"
            >
              {save.isPending ? "Saving…" : dirty ? "Save" : "Saved"}
            </button>
            <button
              onClick={() => reocr.mutate()}
              disabled={reocr.isPending}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
            >
              {reocr.isPending ? "Re-OCR…" : "Re-OCR this page"}
            </button>
            {save.isError && (
              <span className="text-xs text-red-600">
                save failed: {(save.error as Error).message}
              </span>
            )}
            {reocr.isError && (
              <span className="text-xs text-red-600">
                ocr failed: {(reocr.error as Error).message}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
