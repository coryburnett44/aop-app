import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import { BlocksRenderer } from "../components/cms/BlockRenderer";

export default function CmsPage() {
    const { slug } = useParams();
    const [page, setPage] = useState(null);
    const [error, setError] = useState(false);
    useEffect(() => {
        setError(false);
        api.get(`/pages/${slug}`).then(({ data }) => setPage(data)).catch(() => setError(true));
    }, [slug]);

    if (error) return <div className="max-w-3xl mx-auto p-12"><h1 className="font-heading text-3xl">Page not found</h1></div>;
    if (!page) return <div className="max-w-3xl mx-auto p-12"><div className="h-96 bg-muted rounded-2xl animate-pulse" /></div>;

    const hasBlocks = Array.isArray(page.blocks) && page.blocks.length > 0;

    return (
        <div className="max-w-4xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter leading-[1.05]" data-testid="cms-page-title">{page.title}</h1>
            {hasBlocks ? (
                <div className="mt-8" data-testid="cms-page-blocks">
                    <BlocksRenderer blocks={page.blocks} />
                </div>
            ) : (
                <div className="mt-8 text-lg leading-relaxed whitespace-pre-wrap text-foreground/85" data-testid="cms-page-body">{page.body}</div>
            )}
        </div>
    );
}
