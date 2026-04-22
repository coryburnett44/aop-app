import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";

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

    return (
        <div className="max-w-3xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter leading-[1.05]">{page.title}</h1>
            <div className="mt-8 text-lg leading-relaxed whitespace-pre-wrap text-foreground/85" data-testid="cms-page-body">{page.body}</div>
        </div>
    );
}
