import LabelsManager from '@/components/LabelsManager';

export default function LabelsPage() {
  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold text-[#2A1F1A] mb-2">Entity Labels & Tiers</h1>
      <p className="text-muted-foreground mb-8 text-sm">Define custom PII entity types and configure which tier they belong to.</p>
      <LabelsManager />
    </div>
  );
}
