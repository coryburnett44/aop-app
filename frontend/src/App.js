import "@/App.css";
import { Navigate, Routes, Route } from "react-router-dom";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ProtectedRoute from "./components/ProtectedRoute";

import Home from "./pages/Home";
import Login from "./pages/Login";
import Apply from "./pages/Apply";
import Transactions from "./pages/Transactions";
import Events from "./pages/Events";
import EventDetail from "./pages/EventDetail";
import News from "./pages/News";
import NewsDetail from "./pages/NewsDetail";
import Directory from "./pages/Directory";
import Profile from "./pages/Profile";
import CmsPage from "./pages/CmsPage";
import Admin from "./pages/Admin";
import Photos from "./pages/Photos";
import Documents from "./pages/Documents";
import Hours from "./pages/Hours";
import Awards from "./pages/Awards";
import Chapters from "./pages/Chapters";
import Anniversary from "./pages/Anniversary";
import Omega from "./pages/Omega";
import Gear from "./pages/Gear";
import Donations from "./pages/Donations";
import CalendarPage from "./pages/Calendar";
import Chat from "./pages/Chat";
import ScheduleMeeting from "./pages/ScheduleMeeting";
import CheckinScan from "./pages/CheckinScan";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import { SiteSettingsProvider } from "./context/SiteSettingsContext";

function App() {
    return (
        <AuthProvider>
            <SiteSettingsProvider>
                <BrowserRouter>
                <div className="min-h-screen flex flex-col">
                    <Navbar />
                    <main className="flex-1">
                        <Routes>
                            <Route path="/" element={<Home />} />
                            <Route path="/login" element={<Login />} />
                            <Route path="/apply" element={<Apply />} />
                            <Route path="/set-password" element={<Navigate to="/login" replace />} />
                            <Route path="/register" element={<Navigate to="/apply" replace />} />
                            <Route path="/transactions" element={<ProtectedRoute><Transactions /></ProtectedRoute>} />
                            <Route path="/events" element={<ProtectedRoute><Events /></ProtectedRoute>} />
                            <Route path="/events/:id" element={<ProtectedRoute><EventDetail /></ProtectedRoute>} />
                            <Route path="/news" element={<ProtectedRoute><News /></ProtectedRoute>} />
                            <Route path="/news/:id" element={<ProtectedRoute><NewsDetail /></ProtectedRoute>} />
                            <Route path="/directory" element={<ProtectedRoute><Directory /></ProtectedRoute>} />
                            <Route path="/chapters" element={<ProtectedRoute><Chapters /></ProtectedRoute>} />
                            <Route path="/photos" element={<ProtectedRoute><Photos /></ProtectedRoute>} />
                            <Route path="/documents" element={<ProtectedRoute><Documents /></ProtectedRoute>} />
                            <Route path="/awards" element={<ProtectedRoute><Awards /></ProtectedRoute>} />
                            <Route path="/anniversary" element={<ProtectedRoute><Anniversary /></ProtectedRoute>} />
                            <Route path="/omega" element={<ProtectedRoute><Omega /></ProtectedRoute>} />
                            <Route path="/gear" element={<ProtectedRoute><Gear /></ProtectedRoute>} />
                            <Route path="/donations" element={<ProtectedRoute><Donations /></ProtectedRoute>} />
                            <Route path="/calendar" element={<ProtectedRoute><CalendarPage /></ProtectedRoute>} />
                            <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
                            <Route path="/chat/:conversationId" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
                            <Route path="/schedule-meeting" element={<ProtectedRoute><ScheduleMeeting /></ProtectedRoute>} />
                            <Route path="/checkin/:token" element={<CheckinScan />} />
                            <Route path="/forgot-password" element={<ForgotPassword />} />
                            <Route path="/reset-password" element={<ResetPassword />} />
                            <Route path="/hours" element={<ProtectedRoute><Hours /></ProtectedRoute>} />
                            <Route path="/page/:slug" element={<CmsPage />} />
                            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
                            <Route path="/admin" element={<ProtectedRoute adminOnly><Admin /></ProtectedRoute>} />
                        </Routes>
                    </main>
                    <Footer />
                </div>
                <Toaster position="top-right" richColors />
            </BrowserRouter>
            </SiteSettingsProvider>
        </AuthProvider>
    );
}

export default App;
