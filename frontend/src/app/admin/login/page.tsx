'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';

export default function AdminLogin() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const [keepLoggedIn, setKeepLoggedIn] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const token = btoa(`${username}:${password}`);

      const res = await fetch(`${API_BASE_URL}/api/v1/admin/stats`, {
        headers: { 'Authorization': `Basic ${token}` }
      });

      if (!res.ok) throw new Error('Invalid login');
      
      localStorage.setItem('basic_auth', token);
      if (keepLoggedIn) {
        localStorage.setItem('basic_auth_expiry', (Date.now() + 2 * 60 * 60 * 1000).toString());
      }
      router.push('/admin');
    } catch (err) {
      setError('Invalid username or password');
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA] flex items-center justify-center p-4 font-sans">
      <div className="bg-white p-10 rounded-xl border border-[#EAEAEA] shadow-[0_4px_24px_rgba(0,0,0,0.02)] max-w-[400px] w-full">
        <div className="text-center mb-8 flex flex-col items-center">
          <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="w-12 h-12 mb-4 object-contain" />
          <h1 className="text-[22px] font-semibold text-[#111111] tracking-tight">ADOPSHUN AI</h1>
          <p className="text-[13px] text-[#888888] mt-1.5">Sign in to manage your environment</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          {error && <div className="bg-red-50/50 text-red-600 p-3 rounded-md text-[13px] text-center border border-red-100">{error}</div>}
          
          <div className="space-y-3">
            <div>
              <label className="block text-[13px] font-medium text-[#444444] mb-1.5">Username</label>
              <input 
                type="text" 
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB]"
                placeholder="admin"
              />
            </div>
            
            <div className="relative">
              <label className="block text-[13px] font-medium text-[#444444] mb-1.5">Password</label>
              <input 
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 pr-10 text-[14px] bg-[#FAFAFA] border border-[#EAEAEA] rounded-md focus:bg-white focus:border-[#999] focus:ring-0 outline-none transition-all placeholder:text-[#BBBBBB]"
                placeholder="••••••••"
              />
              <button 
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-[30px] text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <input
              type="checkbox"
              id="keepLoggedIn"
              checked={keepLoggedIn}
              onChange={e => setKeepLoggedIn(e.target.checked)}
              className="w-4 h-4 rounded border-[#EAEAEA] text-[#111111] focus:ring-[#111111]"
            />
            <label htmlFor="keepLoggedIn" className="text-[13px] font-medium text-[#444444]">Keep me logged in</label>
          </div>

          <button 
            type="submit" 
            className="w-full py-2.5 bg-[#111111] text-white text-[14px] rounded-md font-medium hover:bg-[#333333] transition-colors mt-6"
          >
            Sign In
          </button>
        </form>
      </div>
    </div>
  );
}
