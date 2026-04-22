import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, adminOnly = false }) {
    const { user, loading } = useAuth();
    if (loading || user === null) {
        return (
            <div className="min-h-[50vh] grid place-items-center" data-testid="auth-loading">
                <div className="animate-pulse text-muted-foreground">Loading…</div>
            </div>
        );
    }
    if (!user) return <Navigate to="/login" replace />;
    if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
    return children;
}
