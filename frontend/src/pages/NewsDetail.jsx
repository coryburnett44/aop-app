import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../lib/api";
import { ArrowLeft } from "lucide-react";
import { format, parseISO } from "date-fns";

export default function NewsDetail() {
    const { id } = useParams();
    const [item, setItem] = useState(null);
    useEffect(() => {
        api.get(`/news/${id}`).then(({ data }) => setItem(data)).catch(() => {});
    }, [id]);
    if (!item) return <div className="max-w-3xl mx-auto p-12"><div className="h-96 bg-muted rounded-2xl animate-pulse" /></div>;
    return (
        <article className="max-w-3xl mx-auto px-6 lg:px-10 py-10">
            <Link to="/news" className="text-sm text-muted-foreground hover:text-primary inline-flex items-center gap-1" data-testid="back-to-news">
                <ArrowLeft className="h-4 w-4" /> All news
            </Link>
            <div className="mt-6">
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                    {item.created_at && format(parseISO(item.created_at), "MMMM d, yyyy")} · by {item.author_name}
                </div>
                <h1 className="font-heading text-4xl sm:text-5xl font-black tracking-tighter mt-3 leading-[1.05]">{item.title}</h1>
                <p className="text-lg text-muted-foreground mt-4 leading-relaxed">{item.summary}</p>
            </div>
            {item.cover_image && (
                <div className="mt-8 rounded-2xl overflow-hidden">
                    <img src={item.cover_image} alt={item.title} className="w-full h-auto object-contain" />
                </div>
            )}
            <div className="mt-8 text-base leading-relaxed whitespace-pre-wrap text-foreground/85">{item.body}</div>
        </article>
    );
}
