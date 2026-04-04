import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    useCallback,
    useMemo,
    useEffect,
    useState,
    useRef,
} from "react";
import { useSearchParams, useNavigate } from "react-router-dom";

import { apiFetch, buildQuery } from "../../api/materials";
import { CelebrateButton } from "../../components/CelebrateButton";
import { NotFoundMaterials } from "../../components/NotFoundMaterials";
import { useContextMenu } from "../../contexts/ContextMenuContext";
import { itemsLabel, itemsLabelLower } from "../../materials/format";
import {
    MaterialStatisticsJson,
    MaterialTagsResponse,
    MaterialTypes,
} from "../../types";

type CompletedResponse = {
    statistics: MaterialStatisticsJson[];
};

function useDebounce<T>(value: T, delay: number): T {
    const [debounced, setDebounced] = useState(value);

    useEffect(() => {
        const id = setTimeout(() => setDebounced(value), delay);
        return () => clearTimeout(id);
    }, [value, delay]);

    return debounced;
}

function Combobox({
                      value,
                      onChange,
                      options,
                      placeholder,
                  }: {
    value: string;
    onChange: (v: string) => void;
    options: string[];
    placeholder?: string;
}) {
    const [open, setOpen] = useState(false);
    const [highlight, setHighlight] = useState(0);
    const ref = useRef<HTMLDivElement>(null);

    const filtered = useMemo(() => {
        return options.filter((o) =>
            o.toLowerCase().includes(value.toLowerCase())
        );
    }, [options, value]);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, []);

    return (
        <div ref={ref} style={{ position: "relative" }}>
            <input
                className="input"
                value={value}
                placeholder={placeholder}
                onFocus={() => setOpen(true)}
                onChange={(e) => {
                    onChange(e.target.value);
                    setOpen(true);
                    setHighlight(0);
                }}
                onKeyDown={(e) => {
                    if (!open) return;

                    if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setHighlight((h) =>
                            Math.min(h + 1, filtered.length - 1)
                        );
                    }
                    if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setHighlight((h) => Math.max(h - 1, 0));
                    }
                    if (e.key === "Enter") {
                        if (filtered[highlight]) {
                            onChange(filtered[highlight]);
                            setOpen(false);
                        }
                    }
                }}
            />

            {open && filtered.length > 0 && (
                <div
                    style={{
                        position: "absolute",
                        top: "100%",
                        left: 0,
                        right: 0,
                        background: "white",
                        border: "1px solid #ccc",
                        zIndex: 10,
                        maxHeight: 200,
                        overflowY: "auto",
                    }}
                >
                    {filtered.map((opt, i) => (
                        <div
                            key={opt}
                            style={{
                                padding: "6px 10px",
                                cursor: "pointer",
                                background:
                                    i === highlight ? "#eee" : "white",
                            }}
                            onMouseEnter={() => setHighlight(i)}
                            onClick={() => {
                                onChange(opt);
                                setOpen(false);
                            }}
                        >
                            {opt}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export function CompletedPage() {
    const qc = useQueryClient();
    const navigate = useNavigate();
    const { open, close } = useContextMenu();

    const [searchParams, setSearchParams] = useSearchParams();

    const [formState, setFormState] = useState({
        material_type: searchParams.get("material_type") ?? "",
        tags_query: searchParams.get("tags_query") ?? "",
        outlined: searchParams.get("outlined") ?? "all",
    });

    useEffect(() => {
        setFormState({
            material_type: searchParams.get("material_type") ?? "",
            tags_query: searchParams.get("tags_query") ?? "",
            outlined: searchParams.get("outlined") ?? "all",
        });
    }, [searchParams]);

    const debouncedForm = useDebounce(formState, 300);

    const [materialTags, setMaterialTags] =
        useState<MaterialTagsResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        void apiFetch<MaterialTagsResponse>("/tags")
            .then(setMaterialTags)
            .catch(() => setError("Failed to load material tags"));
    }, []);

    const queryString = useMemo(() => {
        return buildQuery({
            material_type: debouncedForm.material_type || undefined,
            tags_query: debouncedForm.tags_query || undefined,
            outlined:
                debouncedForm.outlined === "all"
                    ? undefined
                    : debouncedForm.outlined,
        });
    }, [debouncedForm]);

    const q = useQuery({
        queryKey: ["materials", "completed", queryString],
        queryFn: () =>
            apiFetch<CompletedResponse>(`/completed${queryString}`),
    });

    const outlineMut = useMutation({
        mutationFn: (materialId: string) =>
            apiFetch(`/${materialId}/outline`, { method: "POST" }),
        onSuccess: () => {
            void qc.invalidateQueries({ queryKey: ["materials"] });
        },
    });

    const updateURL = useCallback(
        (state: typeof formState) => {
            const next: Record<string, string> = {};

            if (state.material_type) next.material_type = state.material_type;
            if (state.tags_query) next.tags_query = state.tags_query;
            if (state.outlined && state.outlined !== "all") {
                next.outlined = state.outlined;
            }

            setSearchParams(next);
        },
        [setSearchParams]
    );

    const onSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        updateURL(formState);
    };

    const onMaterialContextMenu = useCallback(
        (e: React.MouseEvent, materialId: string) => {
            e.preventDefault();
            close();
            open(e.clientX, e.clientY, [
                {
                    label: "Edit",
                    action: async () =>
                        navigate(`/materials/update?material_id=${materialId}`),
                },
                {
                    label: "Open notes",
                    action: async () =>
                        navigate(`/notes?material_id=${materialId}`),
                },
                {
                    label: "Add note",
                    action: async () =>
                        navigate(`/notes/add?material_id=${materialId}`),
                },
            ]);
        },
        [close, open, navigate]
    );

    const handleOutlinedChange = (value: string) => {
        setFormState((prev) => ({ ...prev, outlined: value }));
    };

    if (q.isLoading) return <p>Loading…</p>;
    if (q.error)
        return <p className="error">{(q.error as Error).message}</p>;

    const stats = q.data?.statistics ?? [];

    return (
        <>
            {error && <div className="alert error">{error}</div>}

            <form id="search-materials-form" onSubmit={onSubmit}>
                <Combobox
                    value={formState.material_type}
                    onChange={(v) =>
                        setFormState((p) => ({ ...p, material_type: v }))
                    }
                    options={MaterialTypes ?? []}
                    placeholder="Choose a material type"
                />

                <Combobox
                    value={formState.tags_query}
                    onChange={(v) =>
                        setFormState((p) => ({ ...p, tags_query: v }))
                    }
                    options={materialTags?.tagsList ?? []}
                    placeholder="Choose material tags"
                />

                <div className="outlined-checkbox">
                    <label>
                        <input
                            type="radio"
                            checked={formState.outlined === "outlined"}
                            onChange={() => handleOutlinedChange("outlined")}
                        />
                        Outlined only
                    </label>

                    <br />

                    <label>
                        <input
                            type="radio"
                            checked={formState.outlined === "not_outlined"}
                            onChange={() => handleOutlinedChange("not_outlined")}
                        />
                        Not outlined only
                    </label>

                    <br />

                    <label>
                        <input
                            type="radio"
                            checked={formState.outlined === "all"}
                            onChange={() => handleOutlinedChange("all")}
                        />
                        All
                    </label>
                </div>

                <button type="submit" className="submit-button">
                    Search
                </button>
            </form>

            {!stats.length ? (
                <NotFoundMaterials kind="completed materials" />
            ) : (
                [...stats]
                    .sort((a, b) => {
                        const ac = a.completed_at ?? a.material.added_at;
                        const bc = b.completed_at ?? b.material.added_at;
                        return String(ac).localeCompare(String(bc));
                    })
                    .map((ms, idx) => {
                        const material = ms.material;
                        const il = itemsLabel(material.material_type);
                        const ill = itemsLabelLower(material.material_type);

                        return (
                            <div
                                key={material.material_id}
                                className="material hover"
                                onContextMenu={(e) =>
                                    onMaterialContextMenu(e, material.material_id)
                                }
                            >
                                <p className="little-text">
                                    {idx + 1} / {stats.length}
                                </p>
                                <p>Title: «{material.title}»</p>
                                <p>Author: {material.authors}</p>
                                <p>
                                    {il}: {material.pages}
                                </p>
                                <p>Type: {material.material_type}</p>
                                {material.tags && <p>Tags: {material.tags}</p>}
                                {material.link && <p>Link: {material.link}</p>}
                                <p>
                                    Is outlined: {material.is_outlined ? "Yes" : "No"}
                                </p>

                                <hr title="Analytics"/>

                                <p>Started at: {ms.started_at}</p>
                                <p>Completed at: {ms.completed_at}</p>
                                <p>Total duration: {ms.total_reading_duration}</p>
                                <p>Notes count: {ms.notes_count}</p>
                                <p>Was being reading: {ms.duration} days</p>
                                <p>Lost time: {ms.lost_time} days</p>
                                <p>
                                    Mean: {ms.mean} {ill} per day
                                </p>

                                {ms.max_record && ms.min_record && (
                                    <>
                                        <hr title="Min/max" />
                                        <p>
                                            Max: {ms.max_record.count} {ill},{" "}
                                            {ms.max_record.date}
                                        </p>
                                        <p>
                                            Min: {ms.min_record.count} {ill},{" "}
                                            {ms.min_record.date}
                                        </p>
                                    </>
                                )}

                                {!material.is_outlined && (
                                    <form
                                        className="outline"
                                        title={`Mark the material id=${material.material_id} as outlined`}
                                        onSubmit={(e) => {
                                            e.preventDefault();
                                            outlineMut.mutate(material.material_id);
                                        }}
                                    >
                                        <CelebrateButton
                                            type="submit"
                                            className="submit-button">
                                            Outline
                                        </CelebrateButton>
                                    </form>
                                )}
                            </div>
                        );
                    })
            )}
        </>
    );
}