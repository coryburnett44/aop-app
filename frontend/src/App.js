import React from "react";
import "./App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Dashboard from "./pages/Dashboard";
import InvoiceForm from "./pages/InvoiceForm";
import PayInvoice from "./pages/PayInvoice";

function App() {
    return (
        <div className="App">
            <Toaster position="top-right" richColors />
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/invoices/new" element={<InvoiceForm mode="create" />} />
                    <Route path="/invoices/:id/edit" element={<InvoiceForm mode="edit" />} />
                    <Route path="/pay/:id" element={<PayInvoice />} />
                </Routes>
            </BrowserRouter>
        </div>
    );
}

export default App;
