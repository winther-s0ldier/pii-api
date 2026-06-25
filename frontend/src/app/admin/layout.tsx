'use client';

import Link from 'next/link';
import { Shield, LayoutDashboard, BookOpen, Users, Cpu, Key } from 'lucide-react';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/useDevAuth';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isSignedIn, isLoaded, orgId, orgRole } = useAuth();

  // RBAC:
  // - Base users (no org) → allowed (solo admin)
  // - Org admins (org:admin) → allowed
  // - Org members (org:member) → blocked
  // - Not signed in → redirect to home
  const isClerkAdmin = isLoaded && isSignedIn && (!orgId || orgRole === 'org:admin');
  const shouldRedirect = isLoaded && !isClerkAdmin;

  useEffect(() => {
    if (shouldRedirect) {
      router.replace('/');
    }
  }, [shouldRedirect, router]);

  useEffect(() => {
    if (!isClerkAdmin) return;
    const tourKey = orgId ? 'hasSeenAdminTour_org' : 'hasSeenAdminTour_base';
    if (localStorage.getItem(tourKey)) return;

    setTimeout(() => {
      const steps = [
        { element: '#admin-nav-dashboard', popover: { title: 'Dashboard', description: 'Overview of your PII activity — request volume, detection rates, and flagged sequences.' } },
        { element: '#admin-nav-labels', popover: { title: 'Entity Labels', description: 'Control which PII types to block, redact, or just audit. Click any label to see what it detects. Drag to change its tier.' } },
        { element: '#admin-nav-dictionary', popover: { title: 'Dictionary', description: 'Add specific words and phrases that should be treated as PII. Built-in labels like api_key are shown here too — you can extend them.' } },
        ...(orgId ? [{ element: '#admin-nav-org', popover: { title: 'Organization', description: 'Manage users, invite members, and configure org-wide policies and quotas.' } }] : []),
      ];

      const driverObj = driver({
        showProgress: true,
        steps,
        onDestroyed: () => localStorage.setItem(tourKey, 'true'),
      });
      driverObj.drive();
    }, 600);
  }, [isClerkAdmin, orgId]);

  // Wait for Clerk to finish loading
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#FAFAFA]">
        <div className="text-sm text-gray-400 animate-pulse">Loading...</div>
      </div>
    );
  }

  // Don't render admin UI while redirecting unauthorized users
  if (!isClerkAdmin) return null;

  return (
    <div className="flex h-screen bg-[#FAFAFA] font-sans text-[#111111]">
      <aside className="w-64 bg-white border-r border-[#EAEAEA] flex flex-col">
        <div className="p-6 border-b border-[#EAEAEA]">
          <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="w-8 h-8 object-contain" />
            <span className="text-lg font-semibold tracking-tight">ADOPSHUN AI</span>
          </Link>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          <Link id="admin-nav-dashboard" href="/admin" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <LayoutDashboard size={18} />
            <span className="font-medium">Dashboard</span>
          </Link>
          <div className="pt-6 pb-2 px-3 text-[11px] font-medium text-[#888888] uppercase tracking-wider">Customization</div>
          <Link id="admin-nav-labels" href="/admin/labels" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <Shield size={18} />
            <span className="font-medium">Entity Labels</span>
          </Link>
          <Link id="admin-nav-dictionary" href="/admin/dictionary" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <BookOpen size={18} />
            <span className="font-medium">Dictionary</span>
          </Link>
          <div className="pt-6 pb-2 px-3 text-[11px] font-medium text-[#888888] uppercase tracking-wider">Integrations</div>
          <Link id="admin-nav-models" href="/admin/models" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <Cpu size={18} />
            <span className="font-medium">Models</span>
          </Link>
          <Link id="admin-nav-api-keys" href="/admin/api-keys" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <Key size={18} />
            <span className="font-medium">API Keys</span>
          </Link>
          {orgId && (
            <>
              <div className="pt-6 pb-2 px-3 text-[11px] font-medium text-[#888888] uppercase tracking-wider">Users</div>
              <Link id="admin-nav-org" href="/admin/organization" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
                <Users size={18} />
                <span className="font-medium">Organization</span>
              </Link>
            </>
          )}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto bg-[#FAFAFA]">
        {children}
      </main>
    </div>
  );
}
