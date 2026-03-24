with open("web/app/portfolio/page.tsx", "r") as f:
    content = f.read()

import re
new_content = re.sub(r'(return \(\n\s*<div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">)', r'\1\n      <div>Risk Context: Hacks & Exploits</div>', content)

with open("web/app/portfolio/page.tsx", "w") as f:
    f.write(new_content)
