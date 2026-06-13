import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { Trophy, Award, Heart, DollarSign, UserPlus, Users } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";

const NAVY = "#0A2463";
const RED = "#C8102E";
const GOLD = "#F9D466";

const ICONS = {
    member_of_year: Trophy,
    chapter_of_year: Award,
    top_cs_member: Heart,
    top_cs_chapter: Heart,
    top_fundraising_member: DollarSign,
    top_fundraising_chapter: DollarSign,
    top_recruiter: UserPlus,
};

/**
 * Home-page widget: current-year winners across all 7 "Of The Year" categories.
 * Hides empty categories so the section stays compact early in the year.
 */
export default function OfTheYearWinners() {
    const [data, setData] = useState(null);

    useEffect(() => {
        api.get("/of-the-year/current").then(({ data }) => setData(data)).catch(() => setData(null));
    }, []);

    if (!data) return null;
    const filledCategories = data.categories.filter((cat) => data.winners[cat]);
    if (filledCategories.length === 0) return null;

    return (
        <section className="py-14 bg-slate-50" data-testid="home-of-the-year">
            <div className="max-w-6xl mx-auto px-6 lg:px-10">
                <div className="text-center mb-8">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>{data.year} Winners</div>
                    <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight flex items-center justify-center gap-3" style={{ color: NAVY }}>
                        <Award className="h-7 w-7 sm:h-9 sm:w-9" style={{ color: GOLD }} />
                        Of The Year
                    </h2>
                    <p className="text-sm sm:text-base text-slate-600 mt-2">Celebrating this year&apos;s standouts across the AOP family.</p>
                </div>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filledCategories.map((cat) => {
                        const w = data.winners[cat];
                        const Icon = ICONS[cat] || Trophy;
                        const isMember = !!w.user_id;
                        const name = isMember ? (w.user_name || "—") : (w.chapter_name || "—");
                        const avatar = isMember ? w.user_avatar_url : w.chapter_logo_url;
                        const avatarSrc = avatar ? mediaUrl(avatar) : null;
                        const initials = (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                        return (
                            <div key={cat} className="bg-white rounded-2xl border-2 border-slate-200 p-5 flex items-center gap-4 hover:border-slate-300 hover:shadow-sm transition-all" data-testid={`oty-winner-${cat}`}>
                                <div className="w-12 h-12 rounded-2xl grid place-items-center shrink-0" style={{ backgroundColor: `${NAVY}15`, color: NAVY }}>
                                    <Icon className="h-6 w-6" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-[10px] uppercase tracking-widest font-bold text-slate-400">{data.labels[cat]}</div>
                                    <div className="flex items-center gap-2 mt-1">
                                        <Avatar className="h-7 w-7">
                                            {avatarSrc && <AvatarImage src={avatarSrc} />}
                                            <AvatarFallback className="text-[10px] bg-primary/10 text-primary">{initials}</AvatarFallback>
                                        </Avatar>
                                        <div className="font-heading font-bold text-base truncate" style={{ color: NAVY }} title={name}>{name}</div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </section>
    );
}
