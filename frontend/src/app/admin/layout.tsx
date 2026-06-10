'use client';

import Link from 'next/link';
import { Shield, LayoutDashboard, BookOpen } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const [isAuth, setIsAuth] = useState(false);
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
    const auth = localStorage.getItem('basic_auth');
    const authExpiry = localStorage.getItem('basic_auth_expiry');
    let isValid = false;
    
    if (auth) {
      if (authExpiry && Date.now() < parseInt(authExpiry, 10)) {
        isValid = true;
      } else if (!authExpiry) {
        // Session-only (no expiry) is also valid
        isValid = true;
      }
    }
    
    if (isValid) {
      setIsAuth(true);
    } else {
      localStorage.removeItem('basic_auth');
      localStorage.removeItem('basic_auth_expiry');
      if (pathname !== '/admin/login') {
        router.push('/admin/login');
      }
    }
  }, [pathname, router]);

  if (!mounted) return null;

  // Don't show sidebar on login page
  if (!isAuth && pathname === '/admin/login') {
    return <>{children}</>;
  }

  if (!isAuth) return null;

  return (
    <div className="flex h-screen bg-[#FAFAFA] font-sans text-[#111111]">
      <aside className="w-64 bg-white border-r border-[#EAEAEA] flex flex-col">
        <div className="p-6 border-b border-[#EAEAEA]">
          <div className="flex items-center gap-3">
            <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="w-8 h-8 object-contain" />
            <span className="text-lg font-semibold tracking-tight">ADOPSHUN AI</span>
          </div>
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
        </nav>
      </aside>
      <main className="flex-1 overflow-auto bg-[#FAFAFA]">
        {children}
      </main>
    </div>
  );
}
