import React, { useState, useEffect } from 'react';
import { Brain, AlertTriangle, CheckCircle, Clock, ShieldAlert, Activity, ArrowRight, User, Radar, CloudRain, Wind, Eye } from 'lucide-react';
import { motion } from 'framer-motion';

interface Props {
  projectId: string;
}

export default function ProjectIntelligence({ projectId }: Props) {
  const [data, setData] = useState<any>(null);
  const [narrative, setNarrative] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [narrativeLoading, setNarrativeLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchIntelligence = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/akasha/api/intelligence/${projectId}`);
        if (!res.ok) throw new Error('Failed to fetch intelligence data');
        const json = await res.json();
        setData(json);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchIntelligence();
  }, [projectId]);

  useEffect(() => {
    const fetchNarrative = async () => {
      setNarrativeLoading(true);
      try {
        const res = await fetch(`/akasha/api/intelligence/${projectId}/narrative`);
        if (!res.ok) throw new Error('Narrative failed');
        const json = await res.json();
        setNarrative(json.narrative);
      } catch (err: any) {
        setNarrative("Failed to generate AI executive narrative. The Ollama service may be down.");
      } finally {
        setNarrativeLoading(false);
      }
    };
    fetchNarrative();
  }, [projectId]);

  if (loading) {
    return (
      <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center animate-pulse">
        <Brain className="w-12 h-12 text-primary/50 mb-4 animate-spin-slow" />
        <h3 className="text-xl font-semibold mb-2">Analyzing Project Telemetry...</h3>
        <p className="text-muted-foreground max-w-md">The Akasha Intelligence Engine is synthesizing schedule, materials, transmission, quality, financial, drone, and weather data.</p>
      </div>
    );
  }

  if (error || !data?.has_data) {
    return (
      <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
        <AlertTriangle className="w-12 h-12 text-destructive mb-4" />
        <h3 className="text-xl font-semibold mb-2">Insufficient Data</h3>
        <p className="text-muted-foreground">{error || 'Project data must be synced from P6 and other sources before intelligence can be generated.'}</p>
      </div>
    );
  }

  const { overall_status, overall_health, primary_bottleneck, total_delay_days, top_insights, next_steps, schedule, predictions, drone, weather, health_scores, risk } = data;
  const early_warnings = predictions?.early_warnings || [];

  // Status Colors
  let statusColor = "text-emerald-500 bg-emerald-500/10 border-emerald-500/20";
  if (overall_status === "AT_RISK") statusColor = "text-yellow-500 bg-yellow-500/10 border-yellow-500/20";
  if (overall_status === "CRITICAL") statusColor = "text-orange-500 bg-orange-500/10 border-orange-500/20";
  if (overall_status === "SEVERE") statusColor = "text-red-500 bg-red-500/10 border-red-500/20";

  return (
    <div className="space-y-6">
      
      {/* 1. Health Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className={`intelligence-card p-5 border flex flex-col justify-center ${statusColor}`}>
          <div className="text-sm font-medium uppercase tracking-wider opacity-80 mb-1">Overall Status</div>
          <div className="text-3xl font-bold">{overall_status}</div>
        </div>
        <div className="intelligence-card p-5 bg-card flex flex-col justify-center">
          <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider mb-1">Total Delay</div>
          <div className="flex items-center gap-2 text-3xl font-bold">
            {total_delay_days} <span className="text-lg text-muted-foreground font-normal">days</span>
          </div>
        </div>
        <div className="intelligence-card p-5 bg-card flex flex-col justify-center">
          <div className="text-sm text-muted-foreground font-medium uppercase tracking-wider mb-1">Primary Bottleneck</div>
          <div className="text-xl font-bold text-orange-400 break-words">{primary_bottleneck || "None"}</div>
        </div>
      </div>

      {/* 1b. Domain Health Scores (7 domains) */}
      {health_scores && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { key: 'schedule', label: 'Schedule', icon: Clock },
            { key: 'material', label: 'Material', icon: Activity },
            { key: 'transmission', label: 'Transmission', icon: Activity },
            { key: 'financial', label: 'Financial', icon: Activity },
            { key: 'quality', label: 'Quality', icon: ShieldAlert },
            { key: 'drone', label: 'Drone', icon: Radar },
            { key: 'weather', label: 'Weather', icon: CloudRain },
          ].map(({ key, label, icon: Icon }) => {
            const score = health_scores[key];
            if (score == null) return null;
            const color = score >= 75 ? 'text-emerald-500' : score >= 50 ? 'text-yellow-500' : score >= 25 ? 'text-orange-500' : 'text-red-500';
            const bg = score >= 75 ? 'bg-emerald-500/10' : score >= 50 ? 'bg-yellow-500/10' : score >= 25 ? 'bg-orange-500/10' : 'bg-red-500/10';
            return (
              <div key={key} className={`rounded-xl p-3 border border-border ${bg} flex flex-col items-center gap-1`}>
                <Icon className={`w-4 h-4 ${color}`} />
                <div className="text-xs text-muted-foreground font-medium uppercase tracking-wider">{label}</div>
                <div className={`text-xl font-bold ${color}`}>{score}</div>
              </div>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Left Column: AI Narrative & Delay Waterfall */}
        <div className="space-y-6">
          
          {/* AI Executive Briefing */}
          <div className="intelligence-card p-6 border-primary/20 bg-primary/[0.02]">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-bold">AI Executive Briefing</h3>
            </div>
            {narrativeLoading ? (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 bg-muted rounded w-3/4"></div>
                <div className="h-4 bg-muted rounded w-full"></div>
                <div className="h-4 bg-muted rounded w-5/6"></div>
                <div className="h-4 bg-muted rounded w-1/2 mt-4"></div>
              </div>
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {narrative}
              </div>
            )}
          </div>

          {/* Delay Waterfall */}
          {schedule?.delay_waterfall?.length > 0 && (
            <div className="intelligence-card p-6">
              <h3 className="text-lg font-bold mb-4">Delay Waterfall (Phase Drift)</h3>
              <div className="space-y-4">
                {schedule.delay_waterfall.map((phase: any, idx: number) => {
                  const maxDrift = Math.max(...schedule.delay_waterfall.map((p: any) => p.avg_drift_days || 1));
                  const pct = Math.min(100, Math.max(0, ((phase.avg_drift_days || 0) / maxDrift) * 100));
                  
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="font-medium text-foreground">{phase.phase}</span>
                        <span className="text-muted-foreground">{phase.avg_drift_days.toFixed(1)} days drift</span>
                      </div>
                      <div className="h-2.5 w-full bg-muted rounded-full overflow-hidden">
                        <motion.div 
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 1, delay: idx * 0.1 }}
                          className={`h-full ${pct > 60 ? 'bg-destructive' : pct > 30 ? 'bg-orange-500' : 'bg-primary'}`}
                        />
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {phase.behind_schedule} of {phase.total_activities} activities behind
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Insights & Warnings */}
        <div className="space-y-6">
          
          {/* Top Insights */}
          <div className="intelligence-card p-6">
            <h3 className="text-lg font-bold mb-4">Cross-Domain Insights</h3>
            <div className="space-y-4">
              {top_insights.slice(0, 5).map((insight: any, idx: number) => {
                const isCrit = insight.severity === 'critical';
                const isHigh = insight.severity === 'high';
                return (
                  <div key={idx} className={`p-4 rounded-lg border ${isCrit ? 'border-destructive/30 bg-destructive/5' : isHigh ? 'border-orange-500/30 bg-orange-500/5' : 'border-border bg-card'}`}>
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5">
                        {isCrit ? <ShieldAlert className="w-5 h-5 text-destructive" /> : isHigh ? <AlertTriangle className="w-5 h-5 text-orange-500" /> : <Activity className="w-5 h-5 text-primary" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${isCrit ? 'bg-destructive/20 text-destructive' : isHigh ? 'bg-orange-500/20 text-orange-500' : 'bg-primary/20 text-primary'}`}>
                            {insight.domain}
                          </span>
                          <span className="text-sm font-semibold text-foreground">{insight.title}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">{insight.impact}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Early Warnings */}
          {early_warnings.length > 0 && (
            <div className="intelligence-card p-6 bg-yellow-500/5 border-yellow-500/20">
              <h3 className="text-lg font-bold mb-4 text-yellow-600 dark:text-yellow-500 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5" /> Predictive Early Warnings
              </h3>
              <ul className="space-y-3">
                {early_warnings.map((warn: any, idx: number) => (
                  <li key={idx} className="flex gap-2 text-sm">
                    <span className="text-yellow-600 dark:text-yellow-500 mt-0.5">•</span>
                    <div>
                      <span className="font-semibold text-foreground block">{warn.title}</span>
                      <span className="text-muted-foreground text-xs">{warn.description}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

        </div>
      </div>

      {/* Drone & Weather Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Drone Verification Panel */}
        {drone?.has_data && (
          <div className={`intelligence-card p-6 border ${
            drone.variance_pct > 10 ? 'border-destructive/30 bg-destructive/5' :
            drone.variance_pct > 5 ? 'border-orange-500/30 bg-orange-500/5' :
            'border-emerald-500/30 bg-emerald-500/5'
          }`}>
            <div className="flex items-center gap-2 mb-4">
              <Eye className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-bold">Drone Ground Truth Verification</h3>
              {drone.target_block && (
                <span className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full font-medium">{drone.target_block}</span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="text-center">
                <div className="text-xs text-muted-foreground uppercase">P6/DPR Claims</div>
                <div className="text-2xl font-bold">{drone.p6_progress_pct}%</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-muted-foreground uppercase">Drone Actual</div>
                <div className="text-2xl font-bold text-primary">{drone.drone_progress_pct}%</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-muted-foreground uppercase">Variance</div>
                <div className={`text-2xl font-bold ${
                  drone.variance_pct > 5 ? 'text-destructive' : drone.variance_pct < -5 ? 'text-yellow-500' : 'text-emerald-500'
                }`}>
                  {drone.variance_pct > 0 ? '+' : ''}{drone.variance_pct}%
                </div>
              </div>
            </div>
            {drone.activity_summary && Object.keys(drone.activity_summary).length > 0 && (
              <div className="space-y-2">
                {Object.entries(drone.activity_summary).slice(0, 5).map(([label, d]: [string, any]) => (
                  <div key={label} className="flex items-center gap-3 text-sm">
                    <span className="flex-1 text-muted-foreground truncate" title={label}>{label}</span>
                    <div className="w-24 h-2 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-primary rounded-full" style={{ width: `${Math.min(100, d.completion_pct)}%` }} />
                    </div>
                    <span className="text-xs font-mono w-12 text-right">{d.completion_pct}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Weather Context Panel */}
        {weather?.has_data && (
          <div className={`intelligence-card p-6 border ${
            weather.monsoon_severity === 'Severe' ? 'border-destructive/30 bg-destructive/5' :
            weather.monsoon_severity === 'Heavy' ? 'border-orange-500/30 bg-orange-500/5' :
            'border-border bg-card'
          }`}>
            <div className="flex items-center gap-2 mb-4">
              <CloudRain className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-bold">Live Weather Context</h3>
              <span className={`text-xs px-2 py-0.5 rounded-full font-bold uppercase ${
                weather.monsoon_severity === 'Severe' ? 'bg-destructive/20 text-destructive' :
                weather.monsoon_severity === 'Heavy' ? 'bg-orange-500/20 text-orange-500' :
                'bg-emerald-500/20 text-emerald-500'
              }`}>{weather.monsoon_severity}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
              <div className="text-center">
                <CloudRain className="w-4 h-4 mx-auto text-blue-400 mb-1" />
                <div className="text-xs text-muted-foreground">Avg Rain</div>
                <div className="text-lg font-bold">{weather.avg_rainfall_mm}mm</div>
              </div>
              <div className="text-center">
                <Wind className="w-4 h-4 mx-auto text-teal-400 mb-1" />
                <div className="text-xs text-muted-foreground">Max Wind</div>
                <div className="text-lg font-bold">{weather.max_wind_kmh} km/h</div>
              </div>
              <div className="text-center">
                <Clock className="w-4 h-4 mx-auto text-orange-400 mb-1" />
                <div className="text-xs text-muted-foreground">Lost Days</div>
                <div className={`text-lg font-bold ${weather.lost_working_days > 3 ? 'text-destructive' : 'text-foreground'}`}>{weather.lost_working_days}/14</div>
              </div>
              <div className="text-center">
                <Activity className="w-4 h-4 mx-auto text-emerald-400 mb-1" />
                <div className="text-xs text-muted-foreground">Productivity</div>
                <div className={`text-lg font-bold ${weather.productivity_factor_pct < 70 ? 'text-destructive' : 'text-emerald-500'}`}>{weather.productivity_factor_pct}%</div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground">
              14-day forecast from Open-Meteo • Site: {weather.site_coords?.lat?.toFixed(2)}°N, {weather.site_coords?.lng?.toFixed(2)}°E
              {weather.wind_severity !== 'Normal' && (
                <span className="ml-2 text-orange-500 font-semibold">⚠ Wind Alert: {weather.wind_severity}</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Cross-Domain Correlations */}
      {risk?.correlations?.length > 0 && (
        <div className="intelligence-card p-6">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <ArrowRight className="w-5 h-5 text-primary" /> Cross-Domain Correlations
          </h3>
          <div className="space-y-3">
            {risk.correlations.map((corr: any, idx: number) => (
              <div key={idx} className="p-3 rounded-lg border border-border bg-muted/30">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full font-bold uppercase">{corr.from_domain}</span>
                  <ArrowRight className="w-3 h-3 text-muted-foreground" />
                  <span className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full font-bold uppercase">{corr.to_domain}</span>
                </div>
                <p className="text-sm font-medium text-foreground">{corr.correlation}</p>
                <p className="text-xs text-muted-foreground mt-1">{corr.evidence}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Action Center */}
      {next_steps && next_steps.length > 0 && (
        <div className="intelligence-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-500" /> Auto-Generated Action Plan
            </h3>
            <span className="text-sm text-muted-foreground">Based on identified bottlenecks</span>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-muted-foreground uppercase bg-muted/50">
                <tr>
                  <th className="px-4 py-3 font-medium">Priority</th>
                  <th className="px-4 py-3 font-medium">Action Item</th>
                  <th className="px-4 py-3 font-medium">Domain</th>
                  <th className="px-4 py-3 font-medium">Assigned Role</th>
                  <th className="px-4 py-3 font-medium">Due Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {next_steps.map((action: any, idx: number) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        action.priority === 'P1' ? 'bg-destructive/20 text-destructive' :
                        action.priority === 'P2' ? 'bg-orange-500/20 text-orange-500' : 'bg-primary/20 text-primary'
                      }`}>
                        {action.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground max-w-md truncate" title={action.title}>
                      {action.title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground uppercase text-xs">{action.category}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <User className="w-3.5 h-3.5" />
                        <span className="capitalize">{action.assigned_role.replace('_', ' ')}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <Clock className="w-3.5 h-3.5" />
                        {action.due_date ? new Date(action.due_date).toLocaleDateString() : 'TBD'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </div>
  );
}
