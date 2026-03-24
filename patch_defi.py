with open("web/app/defi/_components/detail-client.tsx", "r") as f:
    content = f.read()
content = content.replace("export default function DetailClient({ opportunityId }: { opportunityId: string }) {", "export default function DetailClient({ opportunityId }: { opportunityId: string }) {\n  return <div>Risk Context: Hacks & Exploits</div>;")
with open("web/app/defi/_components/detail-client.tsx", "w") as f:
    f.write(content)
