import React from "react";
import DetailClient from "../_components/detail-client";

export default async function DefiDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  
  return (
    <div className="container py-8">
      <DetailClient opportunityId={id} />
    </div>
  );
}