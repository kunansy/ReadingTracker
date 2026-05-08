import { useState, useCallback, memo } from "react";


type NetworkIframeProps = {
    key: string;
    src: string;
    className?: string;
    title?: string;
};

export const NetworkIframe = memo<NetworkIframeProps>((props: NetworkIframeProps) => {
    const {
        key,
        className = "iframe",
        src,
        title = "Networks graph"
    } = props;

    const [loading, setLoading] = useState(true);
    const [hasError, setHasError] = useState(false);

    const handleLoad = useCallback(() => {
        setLoading(false);
    }, []);

    const handleError = useCallback(() => {
        setLoading(false);
        setHasError(true);
    }, []);

    if (hasError) {
        return (
            <div className={className}>
                <p className="error">Failed to load network graph for note</p>
                <button
                    type="button"
                    onClick={() => {
                        setHasError(false);
                        setLoading(true);
                    }}
                >
                    Retry
                </button>
            </div>
        );
    }

    return (
        <div className={className}>
            {loading && <p className="loading">Loading network graph…</p>}
            <iframe
                className={className}
                src={src}
                key={key}
                title={title}
                sandbox="allow-scripts"
                onLoad={handleLoad}
                onError={handleError}
            />
        </div>
    );
});