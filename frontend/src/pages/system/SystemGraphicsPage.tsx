import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/system";
import { ComboboxInput, ComboboxList, ComboboxRoot } from "../../components/Combobox";

type SystemMetaResponse = {
  material_id: string | null;
  titles: Record<string, string>;
};

type SpanSummary = {
  total: number;
  would_be_total: number;
  zero_days: number;
  mean: number;
  median: number;
  max: { date: string; amount: number };
  min: { date: string; amount: number };
};

type TrackerStatistics = {
  started_at: string;
  finished_at: string;
  duration: number;
  lost_time: number;
  duration_period: string;
  lost_time_period: string;
  lost_time_percent: number;
  mean: number;
  median: number;
  total_materials_completed: number;
  pages_read: Record<string, number>;
  materials_completed: Record<string, number>;
  total_pages_read: number;
  would_be_total: number;
  max_log_record: { count: number; date: string; material_title: string } | null;
  min_log_record: { count: number; date: string; material_title: string } | null;
};

type SystemSummaryResponse = {
  material_id: string;
  last_days: number;
  titles: Record<string, string>;
  tracker_statistics: TrackerStatistics;
  reading_trend: SpanSummary;
  notes_trend: SpanSummary;
  completed_materials_trend: SpanSummary;
  repeated_materials_trend: SpanSummary;
  outlined_materials_trend: SpanSummary;
};

type GraphicResponse = { image: string };

type BackupResponse = {
  materials_count: number;
  reading_log_count: number;
  statuses_count: number;
  notes_count: number;
  cards_count: number;
  repeats_count: number;
  note_repeats_history_count: number;
};

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
        Max: {s.max.amount}, {s.max.date}
      </p>
      <p>
        Min: {s.min.amount}, {s.min.date}
      </p>
    </div>
  );
}

function GraphicBlock({
  title,
  queryKey,
  path,
}: {
  title?: string;
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
      {title ? <h3 className="header">{title}</h3> : null}
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
    queryKey: ["system", "summary", { effectiveMaterialId, lastDays }],
    enabled: !!effectiveMaterialId,
    queryFn: () =>
      apiFetch<SystemSummaryResponse>(
        `/summary${buildQuery({ material_id: effectiveMaterialId, last_days: lastDays })}`,
      ),
    staleTime: 30_000,
  });

  const titles = summaryQ.data?.titles ?? metaQ.data?.titles ?? {};
  const materialOptions = useMemo(() => {
    return Object.keys(titles).sort((a, b) =>
      (titles[a] ?? "").localeCompare(titles[b] ?? ""),
    );
  }, [titles]);

  const backupMut = useMutation({
    mutationFn: () =>
      apiFetch<BackupResponse>("/backup", {
        method: "POST",
      }),
  });

  if (metaQ.isLoading) return <p>Loading…</p>;
  if (metaQ.error) return <p className="error">{(metaQ.error as Error).message}</p>;

  return (
    <>
      {backupMut.data ? (
        <div className="alert success status">
          Success! Backup was created successfully. ({backupMut.data.materials_count}{" "}
          materials, {backupMut.data.reading_log_count} logs,{" "}
          {backupMut.data.statuses_count} statuses, {backupMut.data.notes_count} notes,{" "}
          {backupMut.data.cards_count} cards, {backupMut.data.repeats_count} repeats,{" "}
          {backupMut.data.note_repeats_history_count} note repeats)
        </div>
      ) : null}
      {backupMut.error ? (
        <div className="alert error status">Error! Backup failed.</div>
      ) : null}

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
                  <p>Total pages read: {stat.total_pages_read}</p>
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
            <h3 className="header">Read pages</h3>
            <GraphicBlock
              queryKey={["system", "graphic", "reading-trend", { lastDays }]}
              path={`/graphics/reading-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.reading_trend} />
          </div>

          <div className="graphic-image trend reading-trend">
            <h3 className="header">Total read</h3>
            <GraphicBlock
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
            <h3 className="header">Inserted notes</h3>
            <GraphicBlock
              queryKey={["system", "graphic", "notes-trend", { lastDays }]}
              path={`/graphics/notes-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.notes_trend} />
          </div>

          <div className="graphic-image trend completed-materials-trend">
            <h3 className="header">Completed materials</h3>
            <GraphicBlock
              queryKey={["system", "graphic", "completed-materials-trend", { lastDays }]}
              path={`/graphics/completed-materials-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.completed_materials_trend} />
          </div>

          <div className="graphic-image trend repeated-materials-trend">
            <h3 className="header">Repeated materials</h3>
            <GraphicBlock
              queryKey={["system", "graphic", "repeated-materials-trend", { lastDays }]}
              path={`/graphics/repeated-materials-trend${buildQuery({ last_days: lastDays })}`}
            />
            <SpanStatsBlock s={summaryQ.data.repeated_materials_trend} />
          </div>

          <div className="graphic-image trend outlined-materials-trend">
            <h3 className="header">Outlined materials</h3>
            <GraphicBlock
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

