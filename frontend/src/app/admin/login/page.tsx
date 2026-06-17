'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminLoginPage() {
  const router = useRouter();

  useEffect(() => {
    // ponytail: simple client-side redirection to clean up obsolete route
    router.replace('/admin');
  }, [router]);

  return (
    <div className="flex items-center justify-center h-screen bg-[#FAFAFA]">
      <div className="text-sm text-gray-400 animate-pulse">Redirecting to Admin...</div>
    </div>
  );
}
