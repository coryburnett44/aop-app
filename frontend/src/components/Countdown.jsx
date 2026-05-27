import { useEffect, useState } from "react";

// Target: July 27, 2027 at 12:00 PM Eastern (Atlanta, GA)
const TARGET = new Date("2027-07-27T12:00:00-04:00");

function diffParts(target) {
    const now = new Date();
    let ms = Math.max(0, target.getTime() - now.getTime());
    const days = Math.floor(ms / 86400000);
    ms -= days * 86400000;
    const hours = Math.floor(ms / 3600000);
    ms -= hours * 3600000;
    const minutes = Math.floor(ms / 60000);
    ms -= minutes * 60000;
    const seconds = Math.floor(ms / 1000);
    return { days, hours, minutes, seconds, expired: target.getTime() - new Date().getTime() <= 0 };
}

export default function Countdown() {
    const [parts, setParts] = useState(() => diffParts(TARGET));

    useEffect(() => {
        const t = setInterval(() => setParts(diffParts(TARGET)), 1000);
        return () => clearInterval(t);
    }, []);

    return (
        <section
            className="relative overflow-hidden text-white"
            style={{ background: "linear-gradient(135deg, #0A2463 0%, #0A2463 55%, #C8102E 100%)" }}
            data-testid="anniversary-countdown"
        >
            {/* Star pattern overlay */}
            <div
                className="absolute inset-0 opacity-10 pointer-events-none"
                style={{
                    backgroundImage:
                        "radial-gradient(white 1px, transparent 1.5px), radial-gradient(white 0.5px, transparent 1px)",
                    backgroundSize: "40px 40px, 24px 24px",
                    backgroundPosition: "0 0, 20px 20px",
                }}
            />
            <div className="relative max-w-6xl mx-auto px-6 lg:px-10 py-14">
                <div className="text-center">
                    <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-1.5 text-xs font-bold uppercase tracking-[0.2em] backdrop-blur">
                        <span className="w-2 h-2 rounded-full bg-white animate-pulse-flag" /> Save the date
                    </div>
                    <h2 className="font-heading font-black text-3xl sm:text-4xl lg:text-5xl mt-4 tracking-tight">
                        10 Year Anniversary
                    </h2>
                    <p className="mt-3 text-base sm:text-lg opacity-90">
                        July 27, 2027 · Atlanta, GA
                    </p>
                </div>

                {parts.expired ? (
                    <div className="mt-8 text-center font-heading text-3xl font-bold">🎉 Happy 10th Anniversary, Trendsetters!</div>
                ) : (
                    <div className="mt-10 grid grid-cols-4 gap-3 sm:gap-6 max-w-3xl mx-auto" data-testid="countdown-grid">
                        <Block num={parts.days} label="Days" testid="cd-days" />
                        <Block num={parts.hours} label="Hours" testid="cd-hours" />
                        <Block num={parts.minutes} label="Minutes" testid="cd-minutes" />
                        <Block num={parts.seconds} label="Seconds" testid="cd-seconds" />
                    </div>
                )}
            </div>
        </section>
    );
}

function Block({ num, label, testid }) {
    return (
        <div className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl py-6 px-3 text-center shadow-warm-lg" data-testid={testid}>
            <div className="font-heading font-black text-4xl sm:text-5xl lg:text-6xl tabular-nums leading-none">
                {String(num).padStart(2, "0")}
            </div>
            <div className="text-[10px] sm:text-xs uppercase tracking-widest font-bold mt-2 opacity-80">{label}</div>
        </div>
    );
}
