import React from 'react';
import { Cpu } from 'lucide-react';

export default function ModulePlaceholder({ moduleName }: { moduleName: string }) {
  // Fix acronym capitalization
  const formattedName = moduleName.toLowerCase() === 'dpr' ? 'DPR' 
    : moduleName.toLowerCase() === 'hse' ? 'HSE'
    : moduleName
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');

  // Generate generic but cool sounding features based on the module name
  const isDPR = moduleName.toLowerCase().includes('dpr');
  const isSafety = moduleName.toLowerCase().includes('safety');
  const isEnv = moduleName.toLowerCase().includes('environment');

  const upcomingFeatures = isDPR ? [
    "Automated Daily Progress Aggregation",
    "Real-time Variance Detection",
    "Contractor Performance Tracking",
  ] : isSafety ? [
    "AI-Powered Incident Prediction",
    "Real-time Safety Audits",
    "Safety Trend Analysis",
  ] : isEnv ? [
    "Automated Carbon Accounting",
    "Real-time Environmental Monitoring",
    "Compliance Documentation",
  ] : [
    "Akasha Intelligence Integration",
    "Cross-functional Data Synthesis",
    "Predictive Anomaly Detection",
  ];

  return (
    <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center min-h-[500px]">
      <div className="w-20 h-20 bg-sky-100 dark:bg-sky-500/20 text-sky-500 rounded-full flex items-center justify-center mb-6 shadow-inner">
        <Cpu className="w-10 h-10" />
      </div>
      <h2 className="text-2xl font-bold text-foreground dark:text-white mb-3">{formattedName} Module</h2>
      <p className="text-muted-foreground max-w-md text-[15px] leading-relaxed text-center mb-8">
        Development is currently in progress.<br/>This feature will be available in an upcoming release.
      </p>

      <div className="w-full max-w-md border border-border rounded-xl p-5 bg-card">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-4 text-center">Upcoming Integrations</h3>
        <ul className="space-y-3">
          {upcomingFeatures.map((feature, idx) => (
            <li key={idx} className="flex items-center gap-3 text-[14px] text-foreground/80">
              <div className="w-1.5 h-1.5 rounded-full bg-sky-500/60"></div>
              {feature}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
