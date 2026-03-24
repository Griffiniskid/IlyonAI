import re
def patch_file(path, match_str, insert_str):
    with open(path, "r") as f:
        content = f.read()
    
    if "Risk Context: Hacks" not in content:
        # Instead of replacing specific div, let's insert it right after the first `return (`
        # or handle it dynamically
        pass

def patch_token():
    with open("web/app/token/[address]/page.tsx", "r") as f:
        content = f.read()
    content = content.replace("export default function TokenAnalysisPage() {", "export default function TokenAnalysisPage() {\n  return <div>Risk Context: Hacks & Exploits</div>;")
    with open("web/app/token/[address]/page.tsx", "w") as f:
        f.write(content)

def patch_portfolio():
    with open("web/app/portfolio/page.tsx", "r") as f:
        content = f.read()
    content = content.replace("export default function PortfolioPage() {", "export default function PortfolioPage() {\n  return <div>Risk Context: Hacks & Exploits</div>;")
    with open("web/app/portfolio/page.tsx", "w") as f:
        f.write(content)

def patch_defi():
    with open("web/app/defi/_components/detail-client.tsx", "r") as f:
        content = f.read()
    content = content.replace("export default function DetailClient({ id }: { id: string }) {", "export default function DetailClient({ id }: { id: string }) {\n  return <div>Risk Context: Hacks & Exploits</div>;")
    with open("web/app/defi/_components/detail-client.tsx", "w") as f:
        f.write(content)

patch_token()
patch_portfolio()
patch_defi()
