import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button } from "./ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "./ui/avatar";
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuLabel,
} from "./ui/dropdown-menu";
import { Sparkles, Menu } from "lucide-react";
import { useState } from "react";

const LINKS = [
    { to: "/calendar", label: "Calendar" },
    { to: "/events", label: "Events" },
    { to: "/directory", label: "Members" },
    { to: "/chat", label: "Chat" },
    { to: "/chapters", label: "Chapters" },
    { to: "/photos", label: "Photos" },
    { to: "/documents", label: "AOP Forms" },
    { to: "/awards", label: "Awards" },
    { to: "/gear", label: "Gear" },
    { to: "/donations", label: "Donate" },
    { to: "/omega", label: "Omega" },
    { to: "/news", label: "News" },
];

export default function Navbar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);

    const initials = (user?.name || user?.email || "U")
        .split(" ")
        .map((s) => s[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();

    return (
        <header
            className="sticky top-0 z-40 backdrop-blur-xl bg-[hsl(40_33%_98%_/_0.75)] border-b border-orange-900/10"
            data-testid="main-navbar"
        >
            <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center justify-between">
                <Link to="/" className="flex items-center gap-2 group" data-testid="nav-logo">
                    <div className="w-9 h-9 rounded-2xl bg-[#0A2463] text-white grid place-items-center font-heading font-black text-lg shadow-warm group-hover:rotate-6 transition-transform">
                        A
                    </div>
                    <span className="font-heading font-bold text-xl tracking-tight leading-tight">
                        Alpha<span className="text-[#D62828]"> Omega Phi</span>
                    </span>
                </Link>

                <Link
                    to="/anniversary"
                    className="hidden md:inline-flex items-center gap-1.5 rounded-full px-3 py-1 ml-2 text-[10px] font-bold uppercase tracking-widest text-white shadow-warm hover:-translate-y-0.5 transition-transform"
                    style={{ background: "linear-gradient(135deg, #C8102E 0%, #0A2463 100%)" }}
                    data-testid="nav-anniversary-badge"
                    title="10 Year Anniversary · July 27, 2027 · Atlanta, GA"
                >
                    <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse-flag" />
                    10 Year Anniversary
                </Link>

                <nav className="hidden md:flex items-center gap-1">
                    {user && LINKS.map((l) => (
                        <NavLink
                            key={l.to}
                            to={l.to}
                            data-testid={`nav-link-${l.label.toLowerCase()}`}
                            className={({ isActive }) =>
                                `px-3 py-2 rounded-full text-sm font-medium transition-colors ${
                                    isActive
                                        ? "bg-primary/10 text-primary"
                                        : "text-foreground/70 hover:text-foreground hover:bg-muted"
                                }`
                            }
                        >
                            {l.label}
                        </NavLink>
                    ))}
                </nav>

                <div className="flex items-center gap-2">
                    {user && user !== false ? (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button
                                    className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 bg-muted hover:bg-muted/70 transition-colors"
                                    data-testid="nav-user-menu"
                                >
                                    <Avatar className="h-8 w-8 border border-border">
                                        {user.avatar_url ? <AvatarImage src={user.avatar_url} alt={user.name} /> : null}
                                        <AvatarFallback className="bg-primary/15 text-primary font-semibold text-xs">
                                            {initials}
                                        </AvatarFallback>
                                    </Avatar>
                                    <span className="hidden sm:inline text-sm font-medium truncate max-w-[120px]">
                                        {user.name || user.email}
                                    </span>
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56">
                                <DropdownMenuLabel className="font-heading">
                                    {user.name}
                                    <div className="text-xs font-sans text-muted-foreground font-normal">
                                        {user.email}
                                    </div>
                                </DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => navigate("/profile")} data-testid="menu-profile">
                                    My Profile
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => navigate("/profile?tab=events")} data-testid="menu-my-events">
                                    My Events
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => navigate("/hours")} data-testid="menu-hours">
                                    Volunteer hours
                                </DropdownMenuItem>
                                {user.role === "admin" && (
                                    <>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={() => navigate("/admin")} data-testid="menu-admin">
                                            <Sparkles className="h-4 w-4 mr-2 text-primary" />
                                            Admin Console
                                        </DropdownMenuItem>
                                    </>
                                )}
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                    onClick={async () => {
                                        await logout();
                                        navigate("/");
                                    }}
                                    data-testid="menu-logout"
                                >
                                    Log out
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    ) : (
                        <Button
                            className="rounded-full bg-primary hover:bg-primary/90 shadow-warm"
                            onClick={() => navigate("/login")}
                            data-testid="nav-login-btn"
                        >
                            Member login
                        </Button>
                    )}
                    <button
                        className={`md:hidden rounded-full p-2 hover:bg-muted ${!user ? "hidden" : ""}`}
                        onClick={() => setOpen(!open)}
                        data-testid="mobile-menu-btn"
                        aria-label="Menu"
                    >
                        <Menu className="h-5 w-5" />
                    </button>
                </div>
            </div>
            {open && user && (
                <div className="md:hidden border-t border-border bg-background/95 backdrop-blur-xl" data-testid="mobile-menu">
                    <div className="px-6 py-3 flex flex-col gap-1">
                        {LINKS.map((l) => (
                            <NavLink
                                key={l.to}
                                to={l.to}
                                onClick={() => setOpen(false)}
                                className={({ isActive }) =>
                                    `px-4 py-2 rounded-xl text-sm font-medium ${
                                        isActive ? "bg-primary/10 text-primary" : "hover:bg-muted"
                                    }`
                                }
                            >
                                {l.label}
                            </NavLink>
                        ))}
                    </div>
                </div>
            )}
        </header>
    );
}
