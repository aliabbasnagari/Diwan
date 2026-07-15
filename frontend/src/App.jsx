import { Routes, Route } from "react-router-dom";
import { Disc3 } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import LibraryPage from "./pages/LibraryPage.jsx";
import SpoolerPage from "./pages/SpoolerPage.jsx";
import ConvertPage from "./pages/ConvertPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import TagSuggestionsPage from "./pages/TagSuggestionsPage.jsx";
import { useAuth } from "./auth.jsx";

export default function App() {
  const { status } = useAuth();

  if (status === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Disc3 className="w-7 h-7 text-brass-500 animate-spin" strokeWidth={1.75} />
      </div>
    );
  }

  if (status === "anon") {
    return <LoginPage />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          <Routes>
            <Route path="/" element={<LibraryPage />} />
            <Route path="/spooler" element={<SpoolerPage />} />
            <Route path="/convert" element={<ConvertPage />} />
            <Route path="/tags" element={<TagSuggestionsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
