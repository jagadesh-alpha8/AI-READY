import React, { useState } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { SprintContextBar } from '../components/SprintContextBar';

/** The authenticated app layout every pages/* screen is designed to sit
 * inside: Navbar across the top, Sidebar down the left (linking to the
 * selected sprint's steps), and the page content on the right -- headed by the
 * selected sprint on the dashboard and sprint pages (`showSprintBar`).
 * Below the lg breakpoint the sidebar becomes a slide-in drawer, toggled
 * from the Navbar's hamburger button. */
export const AppShell: React.FC<{ children: React.ReactNode; showSprintBar?: boolean }> = ({
  children,
  showSprintBar = false,
}) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-surface">
      <Navbar onMenuClick={() => setSidebarOpen(true)} />
      <div className="flex">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto w-full">
          {showSprintBar && <SprintContextBar />}
          {children}
        </main>
      </div>
    </div>
  );
};
