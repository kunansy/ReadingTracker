import {
    useMemo,
    useEffect,
    useState,
    useRef
} from "react";

export function Combobox({
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
                cursor: "pointer",
                background:
            i === highlight ? "#eee" : "white",
                padding: ".7vw",
                borderRadius: 20,
                display: "flex",
                margin: "auto",
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

export function MultiCombobox({
                                  values,
                                  onChange,
                                  options,
                                  placeholder,
                              }: {
    values: string[];
    onChange: (v: string[]) => void;
    options: string[];
    placeholder?: string;
}) {
    const [input, setInput] = useState("");
    const [open, setOpen] = useState(false);
    const [highlight, setHighlight] = useState(0);
    const ref = useRef<HTMLDivElement>(null);

    const filtered = useMemo(() => {
        return options.filter(
            (o) =>
                o.toLowerCase().includes(input.toLowerCase()) &&
                !values.includes(o)
        );
    }, [options, input, values]);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (!ref.current?.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, []);

    const addTag = (tag: string) => {
        onChange([...values, tag]);
        setInput("");
        setOpen(false);
    };

    const removeTag = (tag: string) => {
        onChange(values.filter((t) => t !== tag));
    };

    return (
        <div ref={ref} style={{ position: "relative" }}>
    <div className="input" style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
    {values.map((tag) => (
        <span
            key={tag}
        style={{
        background: "#eee",
            padding: ".7vw",
            borderRadius: 20,
            cursor: "pointer",
            display: "flex",
            margin: "auto",
    }}
        onClick={() => removeTag(tag)}
    >
        {tag} ×
          </span>
    ))}

    <input
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
        if (e.key === "Backspace" && !input && values.length) {
            removeTag(values[values.length - 1]);
        }

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
                addTag(filtered[highlight]);
            }
        }
    }}
    />
    </div>

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
                background: i === highlight ? "#eee" : "white",
        }}
            onMouseEnter={() => setHighlight(i)}
            onClick={() => addTag(opt)}
        >
            {opt}
            </div>
        ))}
        </div>
    )}
    </div>
);
}

