'use client';

import Link from 'next/link';
import { Shield, LayoutDashboard, BookOpen, Users } from 'lucide-react';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';

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
          <Link href="/admin" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <LayoutDashboard size={18} />
            <span className="font-medium">Dashboard</span>
          </Link>
          <div className="pt-6 pb-2 px-3 text-[11px] font-medium text-[#888888] uppercase tracking-wider">Customization</div>
          <Link href="/admin/labels" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <Shield size={18} />
            <span className="font-medium">Entity Labels</span>
          </Link>
          <Link href="/admin/dictionary" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
            <BookOpen size={18} />
            <span className="font-medium">Dictionary</span>
          </Link>
          {orgId && (
            <>
              <div className="pt-6 pb-2 px-3 text-[11px] font-medium text-[#888888] uppercase tracking-wider">Users</div>
              <Link href="/admin/organization" className="flex items-center gap-3 px-3 py-2 text-sm text-[#444444] hover:bg-[#F5F5F5] hover:text-[#111111] rounded-md transition-colors">
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
