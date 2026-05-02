import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/system";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox";
import {GraphicResponse, SpanSummary, SystemMetaResponse, SystemSummaryResponse} from "../../types.ts";

function SvgImg({ b64 }: { b64: string }) {
  return <img src={`data:image/svg+xml;base64,${b64}`}  alt="nope"/>;
}

function SpanStatsBlock({ s }: { s: SpanSummary }) {
  return (
    <div className="statistics">
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
  path,
}: {
  title: string;
  queryKey: unknown[];
  path: string;
}) {
  const q = useQuery({
    queryKey,
    queryFn: () => apiFetch<GraphicResponse>(path),
    staleTime: 60_000,
  });

  return (
    <div className="graphic-image trend">
      <h3 className="header">{title}</h3>
      {q.isLoading ? <p>Loading graphic…</p> : null}
      {q.error ? <p className="error">{(q.error as Error).message}</p> : null}
      {q.data?.image ? <SvgImg b64={q.data.image} /> : null}
    </div>
  );
}

export function SystemGraphicsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const materialId = (searchParams.get("material_id") ?? "").trim();
  const lastDays = Number(searchParams.get("last_days") ?? "7") || 7;

  const metaQ = useQuery({
    queryKey: ["system", "meta"],
    queryFn: () => apiFetch<SystemMetaResponse>("/meta"),
    staleTime: 10 * 60_000,
  });

  const effectiveMaterialId = useMemo(() => {
    return materialId || metaQ.data?.material_id || "";
  }, [materialId, metaQ.data?.material_id]);

  const summaryQ = useQuery({
    queryKey: ["system", "summary", { lastDays }],
    queryFn: () =>
      apiFetch<SystemSummaryResponse>(
        `/summary${buildQuery({ last_days: lastDays })}`,
      ),
    staleTime: 30_000,
  });

  const titles = metaQ.data?.titles ?? {};
  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
      (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titles]);

  if (metaQ.isLoading) return <p>Loading…</p>;
  if (metaQ.error) return <p className="error">{(metaQ.error as Error).message}</p>;

  return (
    <>
      <div className="form">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            // no-op: state is pushed on change
          }}
        >
          <ComboboxRoot
            options={materialOptions}
            value={effectiveMaterialId}
            onChange={(next: string) => {
              const p = new URLSearchParams(searchParams);
              if (next) p.set("material_id", next);
              else p.delete("material_id");
              setSearchParams(p, { replace: true });
            }}
            getOptionLabel={(id) => titles[id] ?? ""}
          >
            <ComboboxInput className="input" placeholder="Choose a material" />
            <ComboboxList />
          </ComboboxRoot>

          <input
            className="input"
            type="number"
            placeholder="Enter a count of days"
            value={String(lastDays)}
            title="Show last n days"
            min={1}
            onChange={(e) => {
              const next = e.target.value;
              const p = new URLSearchParams(searchParams);
              if (next) p.set("last_days", next);
              else p.delete("last_days");
              setSearchParams(p, { replace: true });
            }}
          />
        </form>
      </div>

      {summaryQ.isLoading ? <p>Loading statistics…</p> : null}
      {summaryQ.error ? <p className="error">{(summaryQ.error as Error).message}</p> : null}

      {summaryQ.data ? (
        <>
          <div className="tracker-statistics statistics">
            <h3 className="header">Tracker statistics</h3>
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
                  >
                    {Object.entries(stat.materials_completed).map(([material_type, count]) => (
                      <li style={{textTransform: "capitalize"}}> { material_type }: { count } items </li>
                     ))}
                  </ul>
                  <p>Total pages read: {stat.total_pages_read}</p>
                  <ul
                      className="tab-text"
                      style={{ flexDirection: "column" }}
                  >
                    {Object.entries(stat.pages_read).map(([material_type, count]) => (
                        <li style={{textTransform: "capitalize"}}> { material_type }: { count } items </li>
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
          </div>

          <GraphicBlock
            title="Reading progress"
            queryKey={[
              "system",
              "graphic",
              "reading-progress",
              { effectiveMaterialId, lastDays },
            ]}
            path={`/graphics/reading-progress${buildQuery({
              material_id: effectiveMaterialId,
              last_days: lastDays,
            })}`}
          />

          <div className="graphic-image trend reading-trend">
            <GraphicBlock
              title="Read pages"
              queryKey={["system", "graphic", "reading-trend", { lastDays }]}
              path={`/graphics/reading-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.reading_trend} />
          </div>

          <div className="graphic-image trend reading-trend">
            <GraphicBlock
                title="Total read"
                queryKey={["system", "graphic", "total-read", { lastDays }]}
                path={`/graphics/total-read${buildQuery({ last_days: lastDays })}`}
            />
          </div>

          <GraphicBlock
            title="Outline percentage"
            queryKey={["system", "graphic", "outline-percentage"]}
            path="/graphics/outline-percentage"
          />

          <div className="graphic-image trend notes-trend">
            <GraphicBlock
              title="Inserted notes"
              queryKey={["system", "graphic", "notes-trend", { lastDays }]}
              path={`/graphics/notes-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.notes_trend} />
          </div>

          <div className="graphic-image trend completed-materials-trend">
            <GraphicBlock
              title="Completed materials"
              queryKey={["system", "graphic", "completed-materials-trend", { lastDays }]}
              path={`/graphics/completed-materials-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.completed_materials_trend} />
          </div>

          <div className="graphic-image trend repeated-materials-trend">
            <GraphicBlock
              title="Repeated materials"
              queryKey={["system", "graphic", "repeated-materials-trend", { lastDays }]}
              path={`/graphics/repeated-materials-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.repeated_materials_trend} />
          </div>

          <div className="graphic-image trend outlined-materials-trend">
            <GraphicBlock
              title="Outlined materials"
              queryKey={["system", "graphic", "outlined-materials-trend", { lastDays }]}
              path={`/graphics/outlined-materials-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.outlined_materials_trend} />
          </div>
        </>
      ) : null}
    </>
  );
}

