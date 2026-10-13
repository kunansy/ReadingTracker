import { useEffect, useState } from "react";

const SHOW_UP_AFTER_PX = 300;

function scrollBehavior(): ScrollBehavior {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return prefersReducedMotion ? "auto" : "smooth";
}

export function ScrollArrows() {
  const [canScrollUp, setCanScrollUp] = useState(false);
  const [canScrollDown, setCanScrollDown] = useState(false);

  useEffect(() => {
    const update = () => {
      const { scrollHeight } = document.documentElement;
      setCanScrollUp(window.scrollY > SHOW_UP_AFTER_PX);
      setCanScrollDown(window.scrollY + window.innerHeight < scrollHeight - 1);
    };
    update();

    window.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(document.body);

    return () => {
      window.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, []);

  if (!canScrollUp && !canScrollDown) {
    return null;
  }

  return (
    <nav className="scroll-arrows" aria-label="Page scroll">
      {canScrollUp && (
        <button
          type="button"
          aria-label="Scroll to top"
          onClick={() => window.scrollTo({ top: 0, behavior: scrollBehavior() })}
        >
          &#x2191;
        </button>
      )}
      {canScrollDown && (
        <button
          type="button"
          aria-label="Scroll to bottom"
          onClick={() =>
            window.scrollTo({
              top: document.documentElement.scrollHeight,
              behavior: scrollBehavior(),
            })
          }
        >
          &#x2193;
        </button>
      )}
    </nav>
  );
}
