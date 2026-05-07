import { useEffect, useRef, useState, useCallback } from "react";
import { SpellError } from "../types.ts";

export function useSpellChecker(
    content: string,
    setContent: (content: string) => void,
) {
    const [spellErrors, setSpellErrors] = useState<SpellError[]>([]);
    const spellAbortRef = useRef<AbortController | null>(null);
    const debounceRef = useRef<number | null>(null);

    const replaceWord = useCallback((error: SpellError, suggestion: string) => {
        const newContent = content.replaceAll(error.word, suggestion);
        setContent(newContent);

        setSpellErrors(prevErrors => prevErrors.filter(e => e.word !== error.word));
    }, [content, setContent]);

    useEffect(() => {
        if (debounceRef.current !== null) {
            window.clearTimeout(debounceRef.current);
            debounceRef.current = null;
        }
        spellAbortRef.current?.abort();
        spellAbortRef.current = null;

        const text = content.trim();
        if (!text) {
            setSpellErrors([]);
            return;
        }

        debounceRef.current = window.setTimeout(async () => {
            const controller = new AbortController();
            spellAbortRef.current = controller;

            try {
                const resp = await fetch(
                    `https://speller.yandex.net/services/spellservice.json/checkText?text=${encodeURIComponent(content)}`,
                    { method: "GET", signal: controller.signal }
                );

                if (!resp.ok) throw new Error(`Spell checker failed: ${resp.status}`);

                const errata: Array<{ word: string; s?: string[] }> = await resp.json();

                if (!controller.signal.aborted) {
                    setSpellErrors(
                        (errata ?? []).map((e) => ({
                            word: e.word,
                            suggestions: e.s ?? [],
                        }))
                    );
                }
            } catch (e: any) {
                if (e?.name !== "AbortError") setSpellErrors([]);
            } finally {
                if (spellAbortRef.current === controller) spellAbortRef.current = null;
            }
        }, 750);

        return () => {
            if (debounceRef.current !== null) {
                window.clearTimeout(debounceRef.current);
                debounceRef.current = null;
            }
            spellAbortRef.current?.abort();
        };
    }, [content, setContent]);

    return { spellErrors, replaceWord };
}