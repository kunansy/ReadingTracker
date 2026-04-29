import React, {
    createContext,
    useContext,
    useMemo,
    useState,
    useRef,
    useEffect,
    ReactNode,
} from "react";

type ComboboxContextType = {
    open: boolean;
    setOpen: (v: boolean) => void;

    input: string;
    setInput: (v: string) => void;

    options: string[];
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
};

const ComboboxContext = createContext<ComboboxContextType | null>(null);

function useComboboxCtx() {
    const ctx = useContext(ComboboxContext);
    if (!ctx) throw new Error("Combobox components must be inside ComboboxRoot");
    return ctx;
}

type RootProps = {
    children: ReactNode;
    options: string[];
    getOptionLabel?: (opt: string) => string;

    value: string | string[];
    onChange: (v: any) => void;

    multiple?: boolean;
    allowCreate?: boolean;
};

export function ComboboxRoot({
                                 children,
                                 options,
                                 getOptionLabel,
                                 value,
                                 onChange,
                                 multiple = false,
                                 allowCreate = false,
                             }: RootProps) {
    const [open, setOpen] = useState(false);
    const [input, setInput] = useState("");
    const [highlight, setHighlight] = useState(0);

    const ref = useRef<HTMLDivElement>(null);

    const optionLabel = useMemo(() => {
        return getOptionLabel ?? ((opt: string) => opt);
    }, [getOptionLabel]);

    const selected = useMemo<string[]>(() => {
        return multiple ? (value as string[]) : value ? [value as string] : [];
    }, [value, multiple]);

    const filtered = useMemo(() => {
        return options.filter(
            (o) =>
                (o.toLowerCase().includes(input.toLowerCase()) ||
                    optionLabel(o).toLowerCase().includes(input.toLowerCase())) &&
                (!multiple || !selected.includes(o))
        );
    }, [options, input, multiple, selected, optionLabel]);

    const normalized = input.trim();

    const canCreate =
        allowCreate &&
        normalized.length > 0 &&
        !options.some((o) => o.toLowerCase() === normalized.toLowerCase()) &&
        !selected.some((s) => s.toLowerCase() === normalized.toLowerCase());

    const select = (v: string) => {
        if (multiple) {
            onChange([...selected, v]);
            setInput("");
        } else {
            onChange(v);
            setInput(optionLabel(v));
            setOpen(false);
        }
    };

    const remove = (v: string) => {
        if (!multiple) return;
        onChange(selected.filter((s) => s !== v));
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
                setInput,
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
        setInput,
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
                onFocus={() => setOpen(true)}
                onChange={(e) => {
                    setInput(e.target.value);
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
                            select(input.trim());
                        }
                    }
                }}
            />
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
        input,
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
                    onClick={() => select(input.trim())}
                >
                    Create: "{input.trim()}"
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