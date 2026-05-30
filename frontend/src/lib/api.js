import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API,
    headers: { "Content-Type": "application/json" },
});

export const formatUSD = (n) =>
    new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
    }).format(Number(n || 0));

export const formatDate = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
};

export const computeTotals = (items, taxRate, discount) => {
    const subtotal = (items || []).reduce(
        (s, i) => s + Number(i.quantity || 0) * Number(i.rate || 0),
        0,
    );
    const tax = +(subtotal * (Number(taxRate || 0) / 100)).toFixed(2);
    const d = Number(discount || 0);
    const total = Math.max(0, +(subtotal - d + tax).toFixed(2));
    return { subtotal: +subtotal.toFixed(2), tax, discount: +d.toFixed(2), total };
};
