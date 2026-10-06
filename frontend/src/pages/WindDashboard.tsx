import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer 
} from 'recharts';
import { 
  Activity, ArrowLeft, Loader2, AlertTriangle, Wind 
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import TopHeader from '../components/layout/TopHeader';

export default function WindDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/akasha/api/wind/portfolio/cpag')
      .then(res => {
        if (!res.ok) throw new Error('Failed to fetch Wind S-Curve data');
        return res.json();
      })
      .then(json => {
        setData(json.s_curve);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Transform backend chart data for Recharts
  const chartData = data?.chart?.categories?.map((cat: string, index: number) => ({
    category: cat,
    monthly_plan: (data.chart.monthly_plan[index] || 0) * 100,
    monthly_actual: (data.chart.monthly_actual[index] || 0) * 100,
    cum_plan: (data.chart.cum_plan[index] || 0) * 100,
    cum_actual: (data.chart.cum_actual[index] || 0) * 100,
  })) || [];

  return (
    <div className="flex flex-col min-h-screen bg-surface-sunken">
      <TopHeader breadcrumbs={[{ label: 'Wind Portfolio Dashboard' }]} />
      
      <main className="flex-1 p-6 overflow-y-auto">
        <div className="max-w-7xl mx-auto space-y-6">
          
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/ceo-dashboard')}
                className="p-2 -ml-2 rounded-lg text-fg-secondary hover:text-brand-blue hover:bg-surface-1 transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-2xl font-semibold tracking-tight text-fg-primary flex items-center gap-2">
                  <Wind className="w-6 h-6 text-brand-blue" />
                  Wind Portfolio Insights
                </h1>
                <p className="text-sm text-fg-secondary mt-1">
                  Interactive tracking of Overall S-Curve and Gap Analysis
                </p>
              </div>
            </div>
          </div>

          {loading && (
            <div className="flex flex-col items-center justify-center h-64 bg-surface-1 rounded-xl border border-border-subtle">
              <Loader2 className="w-8 h-8 text-brand-blue animate-spin mb-4" />
              <p className="text-fg-secondary font-medium">Loading S-Curve Data...</p>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center h-64 bg-surface-1 rounded-xl border border-status-critical-border bg-status-critical-bg/30">
              <AlertTriangle className="w-8 h-8 text-status-critical-fg mb-4" />
              <p className="text-fg-primary font-medium">{error}</p>
            </div>
          )}

          {!loading && !error && data && (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Interactive Chart Card */}
              <div className="bento-card bg-surface-1 rounded-xl border border-border-subtle overflow-hidden">
                <div className="px-6 py-4 border-b border-border-subtle bg-surface-sunken/40 flex items-center gap-3">
                  <Activity className="w-5 h-5 text-brand-blue" />
                  <h2 className="text-base font-semibold text-fg-primary">Overall S Curve</h2>
                </div>
                <div className="p-6 h-[450px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={chartData}
                      margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border-subtle))" />
                      <XAxis 
                        dataKey="category" 
                        angle={-45}
                        textAnchor="end"
                        tick={{ fontSize: 11, fill: 'hsl(var(--fg-secondary))' }}
                        tickMargin={25}
                        height={60}
                      />
                      <YAxis 
                        yAxisId="left" 
                        label={{ value: 'Monthly Progress (%)', angle: -90, position: 'insideLeft', style: { fill: 'hsl(var(--fg-secondary))', fontSize: 12 } }}
                        tickFormatter={(v) => v.toFixed(1)}
                        tick={{ fontSize: 11, fill: 'hsl(var(--fg-secondary))' }}
                      />
                      <YAxis 
                        yAxisId="right" 
                        orientation="right" 
                        domain={[0, 100]}
                        label={{ value: 'Cumulative Progress (%)', angle: 90, position: 'insideRight', style: { fill: 'hsl(var(--fg-secondary))', fontSize: 12 } }}
                        tickFormatter={(v) => v.toFixed(0)}
                        tick={{ fontSize: 11, fill: 'hsl(var(--fg-secondary))' }}
                      />
                      <Tooltip 
                        contentStyle={{ backgroundColor: 'hsl(var(--surface-1))', borderColor: 'hsl(var(--border-subtle))', borderRadius: '8px' }}
                        itemStyle={{ fontSize: '13px' }}
                        formatter={(value: number, name: string) => [`${value.toFixed(2)}%`, name]}
                      />
                      <Legend wrapperStyle={{ paddingTop: '20px' }} />
                      <Bar yAxisId="left" dataKey="monthly_plan" name="Monthly Plan" fill="#5b9bd5" barSize={20} radius={[2, 2, 0, 0]} />
                      <Bar yAxisId="left" dataKey="monthly_actual" name="Monthly Actual" fill="#70ad47" barSize={20} radius={[2, 2, 0, 0]} />
                      <Line yAxisId="right" type="monotone" dataKey="cum_plan" name="Cumulative Plan" stroke="#4472c4" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                      <Line yAxisId="right" type="monotone" dataKey="cum_actual" name="Cumulative Actual" stroke="#00b050" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Gap Analysis Table */}
              <div className="bento-card bg-surface-1 rounded-xl border border-border-subtle overflow-hidden">
                <div className="px-6 py-4 border-b border-border-subtle bg-surface-sunken/40">
                  <h2 className="text-base font-semibold text-fg-primary">Gap Analysis</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="bg-surface-sunken/60 text-fg-secondary text-xs uppercase tracking-wider">
                      <tr>
                        <th className="px-6 py-3 font-semibold">Parameter</th>
                        <th className="px-6 py-3 font-semibold">Weightage (%)</th>
                        <th className="px-6 py-3 font-semibold">Cumm. Plan (%)</th>
                        <th className="px-6 py-3 font-semibold">Cumm. Actual (%)</th>
                        <th className="px-6 py-3 font-semibold">Variance (%)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle">
                      {data.gap_analysis?.map((row: any, i: number) => (
                        <tr key={i} className="hover:bg-surface-sunken/30 transition-colors">
                          <td className="px-6 py-4 text-fg-primary font-medium">{row.parameter}</td>
                          <td className="px-6 py-4 text-fg-secondary">{row.weight}</td>
                          <td className="px-6 py-4 text-fg-secondary">{row.plan}</td>
                          <td className="px-6 py-4 text-fg-secondary">{row.actual}</td>
                          <td className="px-6 py-4">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                              parseFloat(row.variance) < 0 
                                ? 'bg-status-critical-bg text-status-critical-fg'
                                : 'bg-status-healthy-bg text-status-healthy-fg'
                            }`}>
                              {row.variance}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </main>
    </div>
  );
}
