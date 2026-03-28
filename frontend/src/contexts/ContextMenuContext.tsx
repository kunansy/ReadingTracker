import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type MenuItem = {
  label: string;
  action: () => void | Promise<void>;
};

type Ctx = {
  open: (x: number, y: number, items: MenuItem[]) => void;
  close: () => void;
};

const ContextMenuContext = createContext<Ctx | null>(null);

export function ContextMenuProvider({ children }: { children: ReactNode }) {
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    items: MenuItem[];
  } | null>(null);

  const close = useCallback(() => {
    setMenu(null);
  }, []);

  const open = useCallback((x: number, y: number, items: MenuItem[]) => {
    setMenu({ x, y, items });
  }, []);

  useEffect(() => {
    const hide = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("#context-menu")) {
        return;
      }
      close();
    };
    window.addEventListener("click", hide);
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("click", hide);
      window.removeEventListener("scroll", hide, true);
    };
  }, [close]);

  return (
    <ContextMenuContext.Provider value={{ open, close }}>
      {children}
      <div
        id="context-menu"
        className={menu ? "visible" : ""}
        style={
          menu
            ? {
                position: "fixed",
                left: menu.x,
                top: menu.y,
                zIndex: 1000,
              }
            : undefined
        }
      >
        {menu?.items.map((it, i) => (
          <div
            key={`${it.label}-${i}`}
            className="item"
            onClick={(e) => {
              e.stopPropagation();
              void Promise.resolve(it.action()).finally(() => {
                close();
              });
            }}
          >
            {it.label}
          </div>
        ))}
      </div>
    </ContextMenuContext.Provider>
  );
}

export function useContextMenu(): Ctx {
  const v = useContext(ContextMenuContext);
  if (!v) {
    throw new Error("useContextMenu requires ContextMenuProvider");
  }
  return v;
}
