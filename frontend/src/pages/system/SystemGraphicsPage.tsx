import { useQuery } from "@tanstack/react-query";
import { useMemo, useCallback } from "react";
import { useSearchParams } from "react-router-dom";

import { api, unwrap } from "../../api/client";
import type { GetImageResponse, SpanStatsResponse } from "../../api/schema";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox";
import { useMaterialReadingNow, useReadMaterialTitles } from "../../materials/queries";

function SvgImg({ b64, title }: { b64: string; title: string }) {
  return (
    <figure>
      <img
        style={{
          height: "auto",
          display: "block",
          maxWidth: "100%",
          width: "100%",
        }}
        className="graphicImage"
        src={`data:image/svg+xml;base64,${b64}`}
        alt={`${title} graphic`}
        loading="lazy"
      />
    </figure>
  );
}

function SpanStatsBlock({ s }: { s: SpanStatsResponse }) {
  return (
    <div className="statistics" role="group" aria-label="Span statistics">
      <p>Total: {s.total}</p>
      {"would_be_total" in s ? <p>Would be total: {s.would_be_total}</p> : null}
      <p>Zero days: {s.zero_days}</p>
      <p>Mean: {s.mean}</p>
      <p>Median: {s.median}</p>
      <p>
        Max: {s.max_record.amount}, {s.max_record.date}
      </p>
      <p>
        Min: {s.min_record.amount}, {s.min_record.date}
      </p>
    </div>
  );
}

function GraphicBlock({
  title,
  queryKey,
  load,
  spanSummary,
}: {
  title: string;
  queryKey: unknown[];
  load: () => Promise<GetImageResponse>;
  spanSummary?: SpanStatsResponse;
}) {
  const q = useQuery({
    queryKey,
    queryFn: load,
    staleTime: 60_000,
  });

  return (
    <section className="graphic-image" aria-labelledby={`graphic-header-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <h3 id={`graphic-header-${title.toLowerCase().replace(/\s+/g, '-')}`} className="header">{title}</h3>
      <div role="status" aria-live="polite">
        {q.isLoading ? <p>Loading graphic…</p> : null}
        {q.error ? <p className="error" role="alert">Error: {q.error.message}</p> : null}
      </div>
      {q.data?.image ? <SvgImg b64={q.data.image} title={title} /> : <p>No graphic data available</p>}
      {spanSummary ? <SpanStatsBlock s={spanSummary} /> : null}
    </section>
  );
}

export function SystemGraphicsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const materialId = (searchParams.get("material_id") ?? "").trim();
  const lastDays = Number(searchParams.get("last_days") ?? "7") || 7;

  const materialReadingNowQ = useMaterialReadingNow();

  const materialsTitlesQ = useReadMaterialTitles();

  const effectiveMaterialId = useMemo(() => {
    return materialId || materialReadingNowQ.data?.material_id || "";
  }, [materialId, materialReadingNowQ.data?.material_id]);

  const summaryQ = useQuery({
    queryKey: ["system-graphics", "summary", { lastDays }],
    queryFn: () =>
      unwrap(api.GET("/api/v1/system/summary", { params: { query: { last_days: lastDays } } })),
    staleTime: 30_000,
  });

  const titles = materialsTitlesQ.data?.items ?? {};
  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
      (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titles]);

  const handleMaterialChange = useCallback((next: string) => {
    const p = new URLSearchParams(searchParams);
    if (next) p.set("material_id", next);
    else p.delete("material_id");
    setSearchParams(p, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleDaysChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    const p = new URLSearchParams(searchParams);
    if (next) p.set("last_days", next);
    else p.delete("last_days");
    setSearchParams(p, { replace: true });
  }, [searchParams, setSearchParams]);

  if (materialReadingNowQ.isLoading) return <p role="status">Loading material…</p>;
  if (materialReadingNowQ.error) return <p className="error" role="alert">{materialReadingNowQ.error.message}</p>;

  return (
    <>
      {materialsTitlesQ.error ? (
        <p className="error" role="alert">
          Failed to load materials: {materialsTitlesQ.error.message}
        </p>
      ) : null}
      <section className="form" aria-labelledby="filters-header">
        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <ComboboxRoot
            options={materialOptions}
            value={effectiveMaterialId}
            onChange={handleMaterialChange}
            getOptionLabel={(id) => titles[id] ?? ""}
          >
            <ComboboxInput
              className="input"
              placeholder="Choose a material"
              aria-label="Select material"
            />
            <ComboboxList />
          </ComboboxRoot>

          <input
            id="last-days-input"
            className="input"
            type="number"
            placeholder="Enter a count of days"
            value={String(lastDays)}
            title="Show last n days"
            min={1}
            max={365}
            aria-describedby="days-help"
            onChange={handleDaysChange}
          />
        </form>
      </section>

      <section role="status" aria-live="polite">
        {summaryQ.isLoading ? <p>Loading statistics…</p> : null}
        {summaryQ.error ? <p className="error" role="alert">{summaryQ.error.message}</p> : null}
      </section>

      {summaryQ.data && (
        <>
          <section className="statistics" aria-labelledby="stats-header">
            <h3 id="stats-header" className="header">Tracker statistics</h3>
            {(() => {
              const stat = summaryQ.data.tracker_statistics;
              return (
                <>
                  <p>First record date: {stat.started_at}</p>
                  <p>Last record date: {stat.finished_at}</p>
                  <p>Duration: {stat.duration_period}</p>
                  <p>
                    Lost time: {stat.lost_time_period}, {stat.lost_time_percent}%
                  </p>
                  <p>Mean: {stat.mean}</p>
                  <p>Median: {stat.median}</p>
                  <p>Total materials completed: {stat.total_materials_completed}</p>
                  <ul
                    className="tab-text"
                    style={{ flexDirection: "column" }}
                    role="list"
                  >
                    {Object.entries(stat.materials_completed).map(([material_type, count]) => (
                      <li key={material_type} style={{textTransform: "capitalize"}} role="listitem">
                        {material_type}: {count} items
                      </li>
                    ))}
                  </ul>
                  <p>Total pages read: {stat.total_pages_read}</p>
                  <ul
                    className="tab-text"
                    style={{ flexDirection: "column" }}
                    role="list"
                  >
                    {Object.entries(stat.pages_read).map(([material_type, count]) => (
                      <li key={material_type} style={{textTransform: "capitalize"}} role="listitem">
                        {material_type}: {count} items
                      </li>
                    ))}
                  </ul>
                  <p>Would be total: {stat.would_be_total}</p>
                  {stat.max_log_record ? (
                    <p>
                      Max: {stat.max_log_record.count}, {stat.max_log_record.date},
                      «{stat.max_log_record.material_title}»
                    </p>
                  ) : null}
                  {stat.min_log_record ? (
                    <p>
                      Min: {stat.min_log_record.count}, {stat.min_log_record.date},
                      «{stat.min_log_record.material_title}»
                    </p>
                  ) : null}
                </>
              );
            })()}
          </section>

          {effectiveMaterialId ? (
            <GraphicBlock
              title="Reading progress"
              queryKey={["system-graphics", "reading-progress", { effectiveMaterialId, lastDays }]}
              load={() =>
                unwrap(
                  api.GET("/api/v1/system/graphics/reading-progress", {
                    params: { query: { material_id: effectiveMaterialId, last_days: lastDays } },
                  }),
                )
              }
            />
          ) : null}

          <GraphicBlock
            title="Read pages"
            queryKey={["system-graphics", "reading-trend", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/reading-trend", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
            spanSummary={summaryQ.data.reading_trend}
          />

          <GraphicBlock
            title="Total read"
            queryKey={["system-graphics", "total-read", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/total-read", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
          />

          <GraphicBlock
            title="Outline percentage"
            queryKey={["system-graphics", "outline-percentage"]}
            load={() => unwrap(api.GET("/api/v1/system/graphics/outline-percentage"))}
          />

          <GraphicBlock
            title="Inserted notes"
            queryKey={["system-graphics", "notes-trend", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/notes-trend", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
            spanSummary={summaryQ.data.notes_trend}
          />

          <GraphicBlock
            title="Completed materials"
            queryKey={["system-graphics", "completed-materials-trend", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/completed-materials-trend", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
            spanSummary={summaryQ.data.completed_materials_trend}
          />

          <GraphicBlock
            title="Repeated materials"
            queryKey={["system-graphics", "repeated-materials-trend", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/repeated-materials-trend", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
            spanSummary={summaryQ.data.repeated_materials_trend}
          />

          <GraphicBlock
            title="Outlined materials"
            queryKey={["system-graphics", "outlined-materials-trend", { lastDays }]}
            load={() =>
              unwrap(
                api.GET("/api/v1/system/graphics/outlined-materials-trend", {
                  params: { query: { last_days: lastDays } },
                }),
              )
            }
            spanSummary={summaryQ.data.outlined_materials_trend}
          />
        </>
      )}
    </>
  );
}