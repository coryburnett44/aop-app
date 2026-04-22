import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { Toaster } from "./components/ui/sonner";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import ProtectedRoute from "./components/ProtectedRoute";

import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
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

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <div className="min-h-screen flex flex-col">
                    <Navbar />
                    <main className="flex-1">
                        <Routes>
                            <Route path="/" element={<Home />} />
                            <Route path="/login" element={<Login />} />
                            <Route path="/register" element={<Register />} />
                            <Route path="/events" element={<Events />} />
                            <Route path="/events/:id" element={<EventDetail />} />
                            <Route path="/news" element={<News />} />
                            <Route path="/news/:id" element={<NewsDetail />} />
                            <Route path="/directory" element={<Directory />} />
                            <Route path="/chapters" element={<Chapters />} />
                            <Route path="/photos" element={<Photos />} />
                            <Route path="/documents" element={<Documents />} />
                            <Route path="/awards" element={<Awards />} />
                            <Route
                                path="/hours"
                                element={
                                    <ProtectedRoute>
                                        <Hours />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="/page/:slug" element={<CmsPage />} />
                            <Route
                                path="/profile"
                                element={
                                    <ProtectedRoute>
                                        <Profile />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/admin"
                                element={
                                    <ProtectedRoute adminOnly>
                                        <Admin />
                                    </ProtectedRoute>
                                }
                            />
                        </Routes>
                    </main>
                    <Footer />
                </div>
                <Toaster position="top-right" richColors />
            </BrowserRouter>
        </AuthProvider>
    );
}

export default App;
