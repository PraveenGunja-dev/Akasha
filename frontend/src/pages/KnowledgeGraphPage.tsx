import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { ArrowLeft, Network } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await fetch('/akasha/api/dashboard/knowledge-graph');
        const data = await response.json();
        setGraphData(data);
      } catch (err) {
        console.error("Failed to load knowledge graph", err);
      } finally {
        setLoading(false);
      }
    };
    fetchGraphData();
  }, []);

  const categories = [
    { name: 'Root' },
    { name: 'EPS / SPV' },
    { name: 'Project' },
    { name: 'P6 Schedule' },
    { name: 'SAP Materials' },
    { name: 'Transmission' },
    { name: 'AI Summary' }
  ];

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: function (params: any) {
        if (params.dataType === 'node') {
          return `
            <div class="p-2 bg-background/90 backdrop-blur border border-border rounded-lg shadow-2xl">
               <div class="text-xs text-muted-foreground uppercase font-bold tracking-wider mb-1">${categories[params.data.category]?.name || 'Node'}</div>
               <div class="text-foreground font-semibold text-lg">${params.data.name}</div>
               ${params.data.value ? `<div class="text-sm text-primary mt-1">${params.data.value}</div>` : ''}
            </div>
          `;
        }
        return null;
      }
    },
    legend: [{
      data: categories.map(a => a.name),
      textStyle: { color: '#888' },
      bottom: 20
    }],
    animationDurationUpdate: 1500,
    animationEasingUpdate: 'quinticInOut',
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: graphData.nodes,
        links: graphData.links,
        categories: categories,
        roam: true,
        draggable: true,
        symbol: 'circle',
        label: {
          show: true,
          position: 'right',
          formatter: '{b}',
          color: '#e2e8f0',
          fontSize: 10
        },
        force: {
          repulsion: 300,
          edgeLength: [50, 150],
          gravity: 0.1
        },
        lineStyle: {
          color: 'source',
          curveness: 0.3,
          width: 1.5,
          opacity: 0.6
        },
        itemStyle: {
          borderColor: '#1e293b',
          borderWidth: 2,
          shadowBlur: 10,
          shadowColor: 'rgba(59, 130, 246, 0.5)'
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3
          }
        }
      }
    ]
  };

  return (
    <div className="min-h-screen bg-black relative overflow-hidden flex flex-col">
      {/* Cool Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-500/10 rounded-full blur-[120px] pointer-events-none"></div>

      {/* Header */}
      <div className="p-6 flex items-center justify-between relative z-10 border-b border-white/5 bg-black/50 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors border border-white/10">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl text-white font-light flex items-center gap-3">
              <Network className="w-6 h-6 text-primary" />
              AKASHA <span className="font-bold tracking-widest">KNOWLEDGE GRAPH</span>
            </h1>
            <p className="text-xs text-slate-400 font-mono tracking-widest uppercase mt-1">Live Portfolio Network Topology</p>
          </div>
        </div>
      </div>

      {/* Graph Area */}
      <div className="flex-1 relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-16 h-16 border-4 border-white/10 border-t-primary rounded-full animate-spin"></div>
          </div>
        ) : (
          <ReactECharts 
            option={option} 
            style={{ height: '100%', width: '100%' }} 
            theme="dark"
          />
        )}
      </div>
    </div>
  );
}
