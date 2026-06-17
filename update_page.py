import os
import re

path = "z:/pi-api/frontend/src/app/page.tsx"
with open(path, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Imports
code = code.replace(
    'import "driver.js/dist/driver.css";',
    'import "driver.js/dist/driver.css";\nimport { SignIn, SignedIn, SignedOut, UserButton, useAuth } from "@clerk/nextjs";'
)

# 2. Add useAuth hook
code = code.replace(
    '  const [stagedFile, setStagedFile] = useState<File | null>(null);',
    '  const [stagedFile, setStagedFile] = useState<File | null>(null);\n  const { getToken } = useAuth();'
)

# 3. Replace all headers: { 'Authorization': `Basic ${authHeader}` } with Bearer ${await getToken()}
code = code.replace(
    "`Basic ${authHeader}`",
    "`Bearer ${await getToken()}`"
)

code = code.replace(
    "`Basic ${auth}`",
    "`Bearer ${await getToken()}`"
)

# 4. In loadSessions
code = code.replace(
    "const loadSessions = async (overrideAuth?: string) => {\n    const auth = overrideAuth || authHeader;\n    if (!auth) return;",
    "const loadSessions = async () => {\n"
)

# 5. Remove basic auth UI entirely.
auth_ui_pattern = re.compile(r'if \(!isAuthenticated\) \{.*?(?=return \(\n\s*<div className="flex h-screen)', re.DOTALL)
code = auth_ui_pattern.sub('', code)

# 6. Wrap the remaining layout in SignedIn, and add SignedOut at the top.
return_pattern = re.compile(r'return \(\n\s*<div className="flex h-screen bg-\[#FAF9F5\]')
code = return_pattern.sub(
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
      <SignedIn>
        <div className="flex h-screen bg-[#FAF9F5]''', code)

# Add closing tag for <>
code = code.replace('    </div>\n  );\n}', '    </div>\n      </SignedIn>\n    </>\n  );\n}')

# Add UserButton next to New Chat
code = code.replace(
    '<Plus size={16} /> New chat\n            </button>\n          </div>',
    '<Plus size={16} /> New chat\n            </button>\n            <div className="mt-2 flex items-center gap-2 p-2">\n              <UserButton /> <span className="text-sm font-medium">My Account</span>\n            </div>\n          </div>'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("page.tsx updated successfully!")
