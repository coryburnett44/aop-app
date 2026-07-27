import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ArrowLeft } from "lucide-react";
import { format, parseISO } from "date-fns";
import { mediaUrl } from "../lib/api";

export default function NewsDetail() {
    const { id } = useParams();
    const [item, setItem] = useState(null);
    useEffect(() => {
        api.get(`/news/${id}`).then(({ data }) => setItem(data)).catch(() => {});
    }, [id]);
    if (!item) return <div className="max-w-3xl mx-auto p-12"><div className="h-96 bg-muted rounded-2xl animate-pulse" /></div>;
    const tpl = item.template || "classic";
    const images = (item.images || []).filter(Boolean);
    const wrapperStyle = item.background_color ? { backgroundColor: item.background_color } : undefined;
    return (
        <div style={wrapperStyle} data-testid="news-article-wrapper">
        <article className={tpl === "hero" || tpl === "gallery" ? "max-w-5xl mx-auto px-6 lg:px-10 py-10" : "max-w-4xl mx-auto px-6 lg:px-10 py-10"} data-testid={`news-article-${tpl}`}>
            <Link to="/news" className="text-sm text-muted-foreground hover:text-primary inline-flex items-center gap-1" data-testid="back-to-news">
                <ArrowLeft className="h-4 w-4" /> All news
            </Link>
            {tpl === "hero" && item.cover_image && (
                <div className="mt-6 rounded-2xl overflow-hidden aspect-[21/9] bg-muted">
                    <img src={mediaUrl(item.cover_image)} alt={item.title} className="w-full h-full object-cover" />
                </div>
            )}
            <div className="mt-6">
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                    {item.created_at && format(parseISO(item.created_at), "MMMM d, yyyy")} · by {item.author_name}
                </div>
                <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter mt-3 leading-[1.05]">{item.title}</h1>
                {item.summary && <p className="text-lg text-muted-foreground mt-4 leading-relaxed">{item.summary}</p>}
            </div>
            {tpl !== "hero" && item.cover_image && (
                <div className="mt-8 rounded-2xl overflow-hidden">
                    <img src={mediaUrl(item.cover_image)} alt={item.title} className="w-full h-auto object-contain" />
                </div>
            )}

            <TemplateBody template={tpl} body={item.body} bodyHtml={item.body_html} images={images} title={item.title} />
        </article>
        </div>
    );
}

function TemplateBody({ template, body, bodyHtml, images, title }) {
    // Prefer the rich HTML body when the admin authored it; fall back to the
    // legacy paragraph-split plain text for older articles.
    const hasHtml = bodyHtml && bodyHtml.trim().length > 0;
    const paragraphs = (body || "").split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
    const bodyRich = hasHtml ? (
        <div
            className="tiptap prose prose-sm sm:prose-base max-w-none text-foreground/85 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: bodyHtml }}
        />
    ) : (
        <div className="text-base leading-relaxed whitespace-pre-wrap text-foreground/85">{body}</div>
    );

    // When a rich-HTML body is present we always render it in a single column
    // to preserve formatting; multi-column templates below still surface any
    // image gallery underneath so the layout picker keeps its effect.
    if (hasHtml) {
        if (template === "image_left" || template === "image_right") {
            const isLeft = template === "image_left";
            return (
                <div className="mt-8 grid md:grid-cols-5 gap-8 items-start" data-testid={`tpl-${template}`}>
                    <div className={`md:col-span-2 ${isLeft ? "md:order-1" : "md:order-2"}`}>
                        {images.slice(0, 3).map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-auto object-cover rounded-2xl mb-4" />
                        ))}
                    </div>
                    <div className={`md:col-span-3 ${isLeft ? "md:order-2" : "md:order-1"}`}>
                        {bodyRich}
                    </div>
                    {images.length > 3 && (
                        <div className="md:col-span-5 grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                            {images.slice(3).map((src, i) => (
                                <img key={i} src={mediaUrl(src)} alt={`${title} — extra ${i + 1}`} className="w-full h-40 object-cover rounded-2xl" />
                            ))}
                        </div>
                    )}
                </div>
            );
        }
        return (
            <div className="mt-8" data-testid={`tpl-${template}`}>
                {bodyRich}
                {images.length > 0 && (
                    <div className="mt-8 grid grid-cols-2 md:grid-cols-3 gap-4" data-testid="tpl-image-grid">
                        {images.map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-56 object-cover rounded-2xl" />
                        ))}
                    </div>
                )}
            </div>
        );
    }

    if (template === "two_col") {
        return (
            <div className="mt-8 grid md:grid-cols-2 gap-8 [&_p]:leading-relaxed [&_p]:text-foreground/85 [&_p+p]:mt-4" data-testid="tpl-two-col">
                <div>{paragraphs.slice(0, Math.ceil(paragraphs.length / 2)).map((p, i) => <p key={i}>{p}</p>)}</div>
                <div>{paragraphs.slice(Math.ceil(paragraphs.length / 2)).map((p, i) => <p key={i}>{p}</p>)}</div>
                {images.length > 0 && (
                    <div className="md:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-4 mt-4">
                        {images.map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-56 object-cover rounded-2xl" />
                        ))}
                    </div>
                )}
            </div>
        );
    }
    if (template === "three_col") {
        const chunk = Math.ceil(paragraphs.length / 3);
        return (
            <div className="mt-8 grid md:grid-cols-3 gap-8 [&_p]:leading-relaxed [&_p]:text-foreground/85 [&_p+p]:mt-4" data-testid="tpl-three-col">
                {[0, 1, 2].map((i) => (
                    <div key={i}>{paragraphs.slice(i * chunk, (i + 1) * chunk).map((p, j) => <p key={j}>{p}</p>)}</div>
                ))}
                {images.length > 0 && (
                    <div className="md:col-span-3 grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                        {images.map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-44 object-cover rounded-2xl" />
                        ))}
                    </div>
                )}
            </div>
        );
    }
    if (template === "image_left" || template === "image_right") {
        const isLeft = template === "image_left";
        return (
            <div className={`mt-8 grid md:grid-cols-5 gap-8 items-start`} data-testid={`tpl-${template}`}>
                <div className={`md:col-span-2 ${isLeft ? "md:order-1" : "md:order-2"}`}>
                    {images.slice(0, 3).map((src, i) => (
                        <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-auto object-cover rounded-2xl mb-4" />
                    ))}
                </div>
                <div className={`md:col-span-3 ${isLeft ? "md:order-2" : "md:order-1"} text-base leading-relaxed whitespace-pre-wrap text-foreground/85`}>
                    {body}
                </div>
                {images.length > 3 && (
                    <div className="md:col-span-5 grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                        {images.slice(3).map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — extra ${i + 1}`} className="w-full h-40 object-cover rounded-2xl" />
                        ))}
                    </div>
                )}
            </div>
        );
    }
    if (template === "gallery") {
        // Body paragraphs interleaved with images every 2 paragraphs.
        const chunks = [];
        for (let i = 0; i < paragraphs.length; i += 2) chunks.push(paragraphs.slice(i, i + 2));
        return (
            <div className="mt-8 space-y-8" data-testid="tpl-gallery">
                {chunks.map((chunk, idx) => (
                    <div key={idx}>
                        {chunk.map((p, j) => <p key={j} className="leading-relaxed text-foreground/85 [&+p]:mt-4">{p}</p>)}
                        {images[idx] && (
                            <img
                                src={mediaUrl(images[idx])}
                                alt={`${title} — ${idx + 1}`}
                                className="w-full max-h-96 object-cover rounded-2xl mt-6"
                            />
                        )}
                    </div>
                ))}
                {images.length > chunks.length && (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {images.slice(chunks.length).map((src, i) => (
                            <img key={i} src={mediaUrl(src)} alt={`${title} — extra ${i + 1}`} className="w-full h-56 object-cover rounded-2xl" />
                        ))}
                    </div>
                )}
            </div>
        );
    }
    // classic + hero fall through to plain body followed by image grid.
    return (
        <>
            <div className="mt-8 text-base leading-relaxed whitespace-pre-wrap text-foreground/85">{body}</div>
            {images.length > 0 && (
                <div className="mt-8 grid grid-cols-2 md:grid-cols-3 gap-4" data-testid="tpl-image-grid">
                    {images.map((src, i) => (
                        <img key={i} src={mediaUrl(src)} alt={`${title} — ${i + 1}`} className="w-full h-56 object-cover rounded-2xl" />
                    ))}
                </div>
            )}
        </>
    );
}
