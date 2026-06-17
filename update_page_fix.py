import os

path = "z:/pi-api/frontend/src/app/page.tsx"
with open(path, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Fix imports
code = code.replace(
    'import { SignIn, SignedIn, SignedOut, UserButton, useAuth } from "@clerk/nextjs";',
    'import { SignIn, UserButton, useAuth } from "@clerk/nextjs";'
)

# 2. Add isSignedIn check
code = code.replace(
    '  const { getToken } = useAuth();',
    '  const { getToken, isLoaded, isSignedIn } = useAuth();'
)

# 3. Replace SignedOut and SignedIn JSX with pure conditional rendering
code = code.replace(
    '''return (
    <>
      <SignedOut>
        <div className="flex items-center justify-center h-screen bg-[#FAF9F5] font-sans text-[#2A1F1A]">
          <div className="bg-white p-8 rounded-xl shadow-lg w-full max-w-sm border border-[#E0D9C8]">
            <div className="flex justify-center mb-6 text-primary">
              <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="h-12 w-auto object-contain" />
            </div>
            <SignIn routing="hash" />
          </div>
        </div>
      </SignedOut>
      <SignedIn>''',
    '''if (!isLoaded) return <div className="h-screen flex items-center justify-center bg-[#FAF9F5]">Loading Secure Environment...</div>;
  
  if (!isSignedIn) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#FAF9F5] font-sans text-[#2A1F1A]">
        <div className="bg-white p-8 rounded-xl shadow-lg w-full max-w-sm border border-[#E0D9C8]">
          <div className="flex justify-center mb-6 text-primary">
            <img src="/logo-t.png" alt="ADOPSHUN AI Logo" className="h-12 w-auto object-contain" />
          </div>
          <SignIn routing="hash" />
        </div>
      </div>
    );
  }

  return ('''
)

# 4. Remove closing tags
code = code.replace(
    '''      </SignedIn>
    </>
  );
}''',
    '''  );
}'''
)

# Fix double return from previous regex glitch if any
if 'return (\nreturn (\n' in code:
    code = code.replace('return (\nreturn (\n', 'return (\n')

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("page.tsx updated successfully!")
