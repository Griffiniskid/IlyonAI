interface WalletAddressPageProps {
  params: {
    address: string;
  };
}

export default function WalletAddressPage({ params }: WalletAddressPageProps) {
  return (
    <section className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Wallet</h1>
      <p className="text-muted-foreground">Address: {params.address}</p>
    </section>
  );
}
