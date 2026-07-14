import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import LibraryPage from "./pages/LibraryPage.jsx";
import SpoolerPage from "./pages/SpoolerPage.jsx";
import ConvertPage from "./pages/ConvertPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          <Routes>
            <Route path="/" element={<LibraryPage />} />
            <Route path="/spooler" element={<SpoolerPage />} />
            <Route path="/convert" element={<ConvertPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
