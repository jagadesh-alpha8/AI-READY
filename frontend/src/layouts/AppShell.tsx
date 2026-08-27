import React, { useState } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';

/** The authenticated app layout every pages/* screen is designed to sit
 * inside: Navbar across the top, Sidebar down the left (aware of whichever
 * sprint is currently in the URL), and the page content on the right.
 * Below the lg breakpoint the sidebar becomes a slide-in drawer, toggled
 * from the Navbar's hamburger button. */
export const AppShell: React.FC<{ children: React.ReactNode; activeSprintId?: string }> = ({
  children,
  activeSprintId,
}) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-surface">
      <Navbar onMenuClick={() => setSidebarOpen(true)} />
      <div className="flex">
        <Sidebar activeSprintId={activeSprintId} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto w-full">{children}</main>
      </div>
    </div>
  );
};
