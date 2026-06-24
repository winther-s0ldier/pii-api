'use client';
import { useAuth as useClerkAuth } from '@clerk/nextjs';

const DEV_BYPASS = process.env.NEXT_PUBLIC_DEV_BYPASS === 'true';

export function useAuth() {
  const clerk = useClerkAuth();
  if (DEV_BYPASS) {
    return {
      ...clerk,
      isLoaded: true,
      isSignedIn: true as const,
      orgId: null,
      orgRole: undefined,
      getToken: async (_opts?: unknown) => 'dev-token',
    };
  }
  return clerk;
}
