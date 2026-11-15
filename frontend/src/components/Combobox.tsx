import React, {
    createContext,
    useContext,
    useMemo,
    useState,
    useRef,
    useEffect,
    useId,
    ReactNode,
} from "react";

import type { SanitizedInput } from "../tags";

type ComboboxContextType = {
    open: boolean;
    setOpen: (v: boolean) => void;

    input: string;
    changeInput: (raw: string) => void;
    notice: string | null;
    noticeId: string;

    options: readonly string[];
    filtered: string[];
    getOptionLabel: (opt: string) => string;

    highlight: number;
    setHighlight: React.Dispatch<React.SetStateAction<number>>;

    multiple: boolean;
    allowCreate: boolean;

    selected: string[];
    select: (v: string) => void;
    remove: (v: string) => void;

    canCreate: boolean;
    created: string;
};

const keepInput = (raw: string): SanitizedInput => ({ value: raw, notice: null });
const trimInput = (input: string) => input.trim();

const ComboboxContext = createContext<ComboboxContextType | null>(null);

function useComboboxCtx() {
    const ctx = useContext(ComboboxContext);
    if (!ctx) throw new Error("Combobox components must be inside ComboboxRoot");
    return ctx;
}

type BaseProps = {
    children: ReactNode;
    options: readonly string[];
    getOptionLabel?: (opt: string) => string;
    allowCreate?: boolean;
    sanitizeInput?: (raw: string) => SanitizedInput;
    toCreated?: (input: string) => string;
};

type SingleProps = BaseProps & {
    multiple?: false;

    value: string;
    onChange: (v: string) => void;
};

type MultiProps = BaseProps & {
    multiple: true;

    value: string[];
    onChange: (v: string[]) => void;
    maxSelected?: number;
};

type RootProps = SingleProps | MultiProps;

export function ComboboxRoot(props: RootProps) {
    const {
        children,
        options,
        getOptionLabel,
        allowCreate = false,
        sanitizeInput = keepInput,
        toCreated = trimInput,
    } = props;

    const multiple = props.multiple === true;
    const maxSelected = props.multiple === true ? props.maxSelected : undefined;

    const [open, setOpen] = useState(false);
    const [input, setInput] = useState("");
    const [notice, setNotice] = useState<string | null>(null);
    const noticeId = useId();

    const changeInput = (raw: string) => {
        const sanitized = sanitizeInput(raw);
        setInput(sanitized.value);
        setNotice(sanitized.notice);
    };
    const [highlight, setHighlight] = useState(0);

    const ref = useRef<HTMLDivElement>(null);

    const optionLabel = useMemo(() => {
        return getOptionLabel ?? ((opt: string) => opt);
    }, [getOptionLabel]);

    const selected = useMemo<string[]>(() => {
        if (multiple) {
            return props.value;
        }

        return props.value ? [props.value] : [];
    }, [multiple, props.value]);

    const filtered = useMemo(() => {
        return options.filter(
            (o) =>
                (o.toLowerCase().includes(input.toLowerCase()) ||
                    optionLabel(o)
                        .toLowerCase()
                        .includes(input.toLowerCase())) &&
                (!multiple || !selected.includes(o)),
        );
    }, [
        options,
        input,
        multiple,
        selected,
        optionLabel,
    ]);

    const created = toCreated(input);
    const isFull = maxSelected !== undefined && selected.length >= maxSelected;
    const shownNotice = notice ?? (isFull ? `At most ${maxSelected} items can be selected` : null);

    const canCreate =
        !isFull &&
        allowCreate &&
        created.length > 0 &&
        !options.some(
            (o) =>
                o.toLowerCase() ===
                created.toLowerCase(),
        ) &&
        !selected.some(
            (s) =>
                s.toLowerCase() ===
                created.toLowerCase(),
        );

    const select = (v: string) => {
        if (multiple) {
            if (isFull) {
                return;
            }
            props.onChange([...selected, v]);
            setInput("");
            setNotice(null);
            return;
        }

        props.onChange(v);
        setInput(optionLabel(v));
        setOpen(false);
    };

    const remove = (v: string) => {
        if (!multiple) {
            return;
        }

        props.onChange(
            selected.filter((s) => s !== v),
        );
    };

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, []);

    useEffect(() => {
        if (!multiple) {
            setInput(selected[0] ? optionLabel(selected[0]) : "");
        }
    }, [selected, multiple, optionLabel]);

    return (
        <ComboboxContext.Provider
            value={{
                open,
                setOpen,
                input,
                changeInput,
                notice: shownNotice,
                noticeId,
                options,
                filtered,
                getOptionLabel: optionLabel,
                highlight,
                setHighlight,
                multiple,
                allowCreate,
                selected,
                select,
                remove,
                canCreate,
                created,
            }}
        >
            <div ref={ref} style={{ position: "relative" }}>
                {children}
            </div>
        </ComboboxContext.Provider>
    );
}

export function ComboboxInput({
                                 placeholder,
                                 id,
                                 title,
                                 className,
                             }: {
    placeholder?: string;
    id?: string;
    title?: string;
    className?: string;
}) {
    const {
        input,
        changeInput,
        notice,
        noticeId,
        open,
        setOpen,
        highlight,
        setHighlight,
        filtered,
        select,
        canCreate,
        multiple,
        selected,
        remove,
        created,
    } = useComboboxCtx();

    return (
        <div
            className={className ?? "input"}
            style={{ display: "flex", flexWrap: "wrap", gap: 4 }}
        >
            {multiple &&
                selected.map((tag) => (
                    <span
                        key={tag}
                        style={{
                            background: "#eee",
                            padding: "4px 8px",
                            borderRadius: 12,
                            cursor: "pointer",
                            display: "flex",
                            margin: "auto",
                        }}
                        onClick={() => remove(tag)}
                    >
            {tag} ×
          </span>
                ))}

            <input
                id={id}
                title={title}
                style={{ border: "none", outline: "none", flex: 1 }}
                value={input}
                placeholder={placeholder}
                aria-describedby={notice ? noticeId : undefined}
                onFocus={() => setOpen(true)}
                onChange={(e) => {
                    changeInput(e.target.value);
                    setOpen(true);
                    setHighlight(0);
                }}
                onKeyDown={(e) => {
                    if (e.key === "Backspace" && multiple && !input && selected.length) {
                        remove(selected[selected.length - 1]);
                    }

                    if (!open) return;

                    if (e.key === "ArrowDown") {
                        e.preventDefault();
                        setHighlight((h) =>
                            Math.min(h + 1, filtered.length + (canCreate ? 0 : -1))
                        );
                    }

                    if (e.key === "ArrowUp") {
                        e.preventDefault();
                        setHighlight((h) => Math.max(h - 1, 0));
                    }

                    if (e.key === "Enter") {
                        e.preventDefault();

                        if (highlight < filtered.length) {
                            select(filtered[highlight]);
                        } else if (canCreate) {
                            select(created);
                        }
                    }
                }}
            />
            <small id={noticeId} aria-live="polite" style={{ flexBasis: "100%" }}>
                {notice}
            </small>
        </div>
    );
}

export function ComboboxList() {
    const {
        open,
        filtered,
        highlight,
        setHighlight,
        select,
        canCreate,
        created,
        getOptionLabel,
    } = useComboboxCtx();

    if (!open || (filtered.length === 0 && !canCreate)) return null;

    return (
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
            {canCreate && (
                <div
                    style={{
                        padding: "6px 10px",
                        cursor: "pointer",
                        fontStyle: "italic",
                        display: "flex",
                        margin: "auto",
                    }}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => select(created)}
                >
                    Create: "{created}"
                </div>
            )}

            {filtered.map((opt, i) => (
                <div
                    key={opt}
                    style={{
                        padding: "6px 10px",
                        cursor: "pointer",
                        background: i === highlight ? "#eee" : "white",
                        display: "flex",
                        margin: "auto",
                    }}
                    onMouseEnter={() => setHighlight(i)}
                    onClick={() => select(opt)}
                >
                    {getOptionLabel(opt)}
                </div>
            ))}
        </div>
    );
}