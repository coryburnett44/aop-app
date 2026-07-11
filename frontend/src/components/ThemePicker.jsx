import { Sun, Moon, Contrast, Monitor, Check } from "lucide-react";
import { useTheme } from "../lib/theme";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "./ui/dropdown-menu";

const OPTIONS = [
    { key: "light",  label: "Light",           icon: Sun,      hint: "Red / white / navy" },
    { key: "dark",   label: "Dark",            icon: Moon,     hint: "Navy-tinted dark" },
    { key: "mono",   label: "Black & white",   icon: Contrast, hint: "High-contrast mono" },
    { key: "system", label: "System",          icon: Monitor,  hint: "Match OS setting" },
];

/**
 * Compact theme switcher for the Navbar user menu.
 *
 * Renders a nested "Theme" dropdown row: hovering / clicking the row
 * opens a submenu with all 4 options. Falls back to a plain popover on
 * touch devices thanks to Radix's built-in behavior.
 *
 * Two rendering modes:
 *   - `variant="menu-item"` (default) — for embedding inside another
 *     DropdownMenu (e.g. the user menu). Renders as a set of
 *     DropdownMenuItems that flip the theme in place.
 *   - `variant="standalone"` — a self-contained pill button with its
 *     own DropdownMenu.
 */
export default function ThemePicker({ variant = "menu-item" }) {
    const { theme, resolvedTheme, setTheme } = useTheme();

    if (variant === "menu-item") {
        return (
            <>
                <DropdownMenuLabel className="text-[10px] uppercase tracking-wider font-bold text-muted-foreground pt-2">
                    Appearance
                </DropdownMenuLabel>
                {OPTIONS.map((opt) => {
                    const active = theme === opt.key;
                    const Icon = opt.icon;
                    return (
                        <DropdownMenuItem
                            key={opt.key}
                            onSelect={(e) => { e.preventDefault(); setTheme(opt.key); }}
                            className={`gap-2 ${active ? "font-semibold" : ""}`}
                            data-testid={`theme-option-${opt.key}`}
                        >
                            <Icon className="h-4 w-4" />
                            <div className="flex-1">
                                <div className="text-sm leading-tight">{opt.label}</div>
                                <div className="text-[10px] text-muted-foreground leading-tight">
                                    {opt.hint}{opt.key === "system" && ` · currently ${resolvedTheme}`}
                                </div>
                            </div>
                            {active && <Check className="h-4 w-4 text-primary" />}
                        </DropdownMenuItem>
                    );
                })}
            </>
        );
    }

    // Standalone pill button (used outside of an existing menu).
    const Current = OPTIONS.find((o) => o.key === theme) || OPTIONS[0];
    const Icon = Current.icon;
    return (
        <DropdownMenu>
            <DropdownMenuTrigger
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-semibold hover:bg-muted transition-colors"
                data-testid="theme-picker-trigger"
            >
                <Icon className="h-3.5 w-3.5" />
                {Current.label}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="font-heading text-xs">Appearance</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {OPTIONS.map((opt) => {
                    const active = theme === opt.key;
                    const OptIcon = opt.icon;
                    return (
                        <DropdownMenuItem
                            key={opt.key}
                            onSelect={(e) => { e.preventDefault(); setTheme(opt.key); }}
                            className={`gap-2 ${active ? "font-semibold" : ""}`}
                            data-testid={`theme-option-${opt.key}`}
                        >
                            <OptIcon className="h-4 w-4" />
                            <div className="flex-1">
                                <div className="text-sm leading-tight">{opt.label}</div>
                                <div className="text-[10px] text-muted-foreground leading-tight">
                                    {opt.hint}{opt.key === "system" && ` · ${resolvedTheme}`}
                                </div>
                            </div>
                            {active && <Check className="h-4 w-4 text-primary" />}
                        </DropdownMenuItem>
                    );
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
