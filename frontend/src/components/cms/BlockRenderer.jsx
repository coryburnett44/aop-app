import { mediaUrl } from "../../lib/api";

/**
 * Renders a single CMS block to its public-facing output.
 * Block shape: { id, type, props }
 */
export function BlockRenderer({ block }) {
    if (!block) return null;
    const p = block.props || {};
    switch (block.type) {
        case "heading":
            return (
                <h2
                    className="font-heading font-black tracking-tight text-3xl sm:text-4xl lg:text-5xl mt-10 mb-4"
                    style={{ color: p.color || "#0A2463", textAlign: p.align || "left" }}
                    data-testid={`block-heading-${block.id}`}
                >
                    {p.text || "Heading"}
                </h2>
            );
        case "subheading":
            return (
                <h3
                    className="font-heading font-bold text-xl sm:text-2xl mt-6 mb-2"
                    style={{ color: p.color || "#0A2463", textAlign: p.align || "left" }}
                    data-testid={`block-subheading-${block.id}`}
                >
                    {p.text || "Subheading"}
                </h3>
            );
        case "paragraph":
            return (
                <p
                    className="text-base sm:text-lg leading-relaxed text-slate-700 mb-4 whitespace-pre-wrap"
                    style={{ textAlign: p.align || "left" }}
                    data-testid={`block-paragraph-${block.id}`}
                >
                    {p.text || ""}
                </p>
            );
        case "image":
            return (
                <figure className="my-6" data-testid={`block-image-${block.id}`}>
                    <img
                        src={mediaUrl(p.url) || p.url}
                        alt={p.alt || ""}
                        className="w-full rounded-2xl object-contain"
                        style={{ maxHeight: p.max_height ? `${p.max_height}px` : undefined }}
                        loading="lazy"
                    />
                    {p.caption ? (
                        <figcaption className="text-xs text-slate-500 mt-2 text-center">{p.caption}</figcaption>
                    ) : null}
                </figure>
            );
        case "button":
            return (
                <div className="my-6" style={{ textAlign: p.align || "left" }} data-testid={`block-button-${block.id}`}>
                    <a
                        href={p.href || "#"}
                        target={p.target || "_self"}
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-warm-lg hover:-translate-y-0.5 transition-all"
                        style={{ backgroundColor: p.color || "#C8102E" }}
                    >
                        {p.label || "Click here"}
                    </a>
                </div>
            );
        case "divider":
            return <hr className="my-8 border-t-2" style={{ borderColor: p.color || "#0A2463", opacity: 0.2 }} data-testid={`block-divider-${block.id}`} />;
        case "spacer":
            return <div data-testid={`block-spacer-${block.id}`} style={{ height: `${p.height || 40}px` }} />;
        case "video":
            return (
                <div className="my-6 aspect-video rounded-2xl overflow-hidden bg-black" data-testid={`block-video-${block.id}`}>
                    <iframe
                        src={p.url || ""}
                        title={p.title || "video"}
                        className="w-full h-full"
                        frameBorder="0"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                    />
                </div>
            );
        case "html":
            return (
                <div
                    className="prose max-w-none my-4"
                    data-testid={`block-html-${block.id}`}
                    dangerouslySetInnerHTML={{ __html: p.html || "" }}
                />
            );
        case "columns": {
            const cols = Math.max(2, Math.min(4, p.cols || 2));
            const gridClass = { 2: "md:grid-cols-2", 3: "md:grid-cols-3", 4: "md:grid-cols-4" }[cols];
            return (
                <div className={`grid grid-cols-1 ${gridClass} gap-6 my-6`} data-testid={`block-columns-${block.id}`}>
                    {(p.items || []).map((it, idx) => (
                        <div key={idx} className="bg-white border border-slate-200 rounded-2xl p-5">
                            {it.image ? (
                                <img src={mediaUrl(it.image) || it.image} alt="" className="w-full aspect-video object-contain rounded-xl mb-3" />
                            ) : null}
                            {it.title ? <h4 className="font-heading font-bold text-lg mb-2" style={{ color: "#0A2463" }}>{it.title}</h4> : null}
                            {it.body ? <p className="text-sm text-slate-600 whitespace-pre-wrap">{it.body}</p> : null}
                        </div>
                    ))}
                </div>
            );
        }
        default:
            return null;
    }
}

export function BlocksRenderer({ blocks }) {
    if (!Array.isArray(blocks) || blocks.length === 0) return null;
    return blocks.map((b) => <BlockRenderer key={b.id} block={b} />);
}
