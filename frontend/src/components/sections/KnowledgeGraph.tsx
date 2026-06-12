import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Network, X, ZoomIn, ZoomOut, RotateCcw, ChevronDown, Calendar, Package, Zap, Building2, Truck } from 'lucide-react';

interface GNode {
  id: string; name: string; category: number; value?: string;
  health?: string; progress?: number; delayed?: number; on_track?: number;
  x: number; y: number; radius: number;
  color: string; glowColor: string; labelColor: string;
  level: number; parentIdx: number;
  childCount?: number;
  spv?: string;
  capacity?: number;
  p6?: any;
  sap?: any;
  tc?: any;
}

interface GEdge { src: number; tgt: number; level: number; }
interface Particle { edgeIdx: number; t: number; speed: number; size: number; }

// Light-theme friendly colors
const STYLE = {
  root:    { fill: '#D4A853', glow: '#D4A85325', label: '#8B6914' },
  eps:     { fill: '#7C5CBF', glow: '#7C5CBF20', label: '#5B3FA0' },
  ok:      { fill: '#10B981', glow: '#10B98118', label: '#059669' },
  delayed: { fill: '#EF4444', glow: '#EF444418', label: '#DC2626' },
  vendor:  { fill: '#3B82F6', glow: '#3B82F618', label: '#2563EB' },
};

function getStyle(cat: number, health?: string) {
  if (cat === 0) return STYLE.root;
  if (cat === 1) return STYLE.eps;
  if (cat === 3 || health === 'delayed') return STYLE.delayed;
  if (cat === 4) return STYLE.vendor;
  return STYLE.ok;
}

export default function KnowledgeGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef(0);
  const nodesRef = useRef<GNode[]>([]);
  const edgesRef = useRef<GEdge[]>([]);
  const particlesRef = useRef<Particle[]>([]);
  const startTimeRef = useRef(0);
  const scaleRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const dragRef = useRef({ on: false, lx: 0, ly: 0 });
  const sizeRef = useRef({ w: 0, h: 0 });

  const [selectedNode, setSelectedNode] = useState<GNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ n: 0, e: 0 });

  const buildLayout = useCallback((data: any, w: number, h: number) => {
    const raw = data.nodes || [];
    const rawLinks = data.links || [];
    const cx = w / 2, cy = h / 2;
    const nodes: GNode[] = [];
    const edges: GEdge[] = [];
    const idxMap: Record<string, number> = {};

    const root = raw.filter((n: any) => n.category === 0);
    const epsArr = raw.filter((n: any) => n.category === 1);
    const vendors = raw.filter((n: any) => n.category === 4);

    // Map EPS → children from links
    const epsKids: Record<string, any[]> = {};
    rawLinks.forEach((l: any) => {
      const sn = raw.find((n: any) => n.id === l.source);
      const tn = raw.find((n: any) => n.id === l.target);
      if (sn?.category === 1 && (tn?.category === 2 || tn?.category === 3)) {
        if (!epsKids[l.source]) epsKids[l.source] = [];
        epsKids[l.source].push(tn);
      }
    });

    // Root at center
    if (root[0]) {
      const s = getStyle(0);
      nodes.push({ ...root[0], x: cx, y: cy, radius: 36, color: s.fill, glowColor: s.glow, labelColor: s.label, level: 0, parentIdx: -1 });
      idxMap[root[0].id] = 0;
    }

    // ── EPS: proportional angles + VARIED distances ──
    // More children → further from center → more room for their fan
    const totalKids = epsArr.reduce((sum: number, e: any) => sum + Math.max((epsKids[e.id]?.length || 0), 1), 0);
    const baseR = Math.min(w, h) * 0.28;  // minimum EPS distance — increased
    const maxR = Math.min(w, h) * 0.44;   // maximum EPS distance — fills viewport

    // Seed a deterministic pseudo-random per EPS for organic feel
    const seed = (i: number) => Math.abs(Math.sin(i * 127.1 + 311.7)) * 0.5;

    let currentAngle = -Math.PI / 2;
    epsArr.forEach((n: any, i: number) => {
      const kidCount = epsKids[n.id]?.length || 0;
      const weight = Math.max(kidCount, 1);
      const angleSlice = (weight / totalKids) * Math.PI * 2;
      const midAngle = currentAngle + angleSlice / 2;

      // More children = push further out + slight random variation
      const childFactor = kidCount / Math.max(1, Math.max(...epsArr.map((e: any) => epsKids[e.id]?.length || 1)));
      const epsR = baseR + (maxR - baseR) * childFactor + seed(i) * 30;

      const s = getStyle(1);
      const nodeRadius = Math.max(16, Math.min(26, 14 + kidCount * 1.2));
      const idx = nodes.length;
      nodes.push({
        ...n, x: cx + Math.cos(midAngle) * epsR, y: cy + Math.sin(midAngle) * epsR,
        radius: nodeRadius, color: s.fill, glowColor: s.glow, labelColor: s.label,
        level: 1, parentIdx: 0, childCount: kidCount
      });
      idxMap[n.id] = idx;
      edges.push({ src: 0, tgt: idx, level: 1 });

      // ── Projects: varied distances, organic scatter ──
      const children = (epsKids[n.id] || []).slice(0, 8);
      const projBaseR = 100 + kidCount * 12;      // more kids → spread much further
      const projMaxR = projBaseR + 70;
      const fanAngle = Math.min(angleSlice * 0.85, Math.PI * 1.0);
      const fanStart = midAngle - fanAngle / 2;

      children.forEach((child: any, ci: number) => {
        const step = children.length > 1 ? fanAngle / (children.length - 1) : 0;
        const childAngle = fanStart + step * ci;
        // Alternate near/far for organic look
        const dist = projBaseR + (projMaxR - projBaseR) * seed(ci * 7 + i * 13);
        const s2 = getStyle(child.category, child.health);
        const cIdx = nodes.length;
        nodes.push({
          ...child,
          x: nodes[idx].x + Math.cos(childAngle) * dist,
          y: nodes[idx].y + Math.sin(childAngle) * dist,
          radius: 8, color: s2.fill, glowColor: s2.glow, labelColor: s2.label,
          level: 2, parentIdx: idx
        });
        idxMap[child.id] = cIdx;
        edges.push({ src: idx, tgt: cIdx, level: 2 });
      });

      currentAngle += angleSlice;
    });

    // Vendors — further out, organic offset
    const vendorLinks: { vid: string; pid: string }[] = [];
    rawLinks.forEach((l: any) => {
      const sn = raw.find((n: any) => n.id === l.source);
      const tn = raw.find((n: any) => n.id === l.target);
      if ((sn?.category === 2 || sn?.category === 3) && tn?.category === 4)
        vendorLinks.push({ vid: tn.id, pid: sn.id });
    });
    const placedV = new Set<string>();
    vendorLinks.forEach(({ vid, pid }, vi) => {
      if (placedV.has(vid)) return;
      placedV.add(vid);
      const vRaw = vendors.find((v: any) => v.id === vid);
      const pIdx = idxMap[pid];
      if (!vRaw || pIdx === undefined) return;
      const p = nodes[pIdx];
      const a = Math.atan2(p.y - cy, p.x - cx);
      const s = getStyle(4);
      const idx = nodes.length;
      nodes.push({ ...vRaw, x: p.x + Math.cos(a) * 50, y: p.y + Math.sin(a) * 50, radius: 6, color: s.fill, glowColor: s.glow, labelColor: s.label, level: 3, parentIdx: pIdx });
      idxMap[vRaw.id] = idx;
      edges.push({ src: pIdx, tgt: idx, level: 3 });
    });

    // Particles
    const particles: Particle[] = [];
    edges.forEach((_, i) => {
      const count = 1 + Math.floor(Math.random() * 2);
      for (let j = 0; j < count; j++)
        particles.push({ edgeIdx: i, t: Math.random(), speed: 0.001 + Math.random() * 0.003, size: 1 + Math.random() * 1.5 });
    });

    nodesRef.current = nodes;
    edgesRef.current = edges;
    particlesRef.current = particles;
    setStats({ n: nodes.length, e: edges.length });
    startTimeRef.current = performance.now() / 1000;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/akasha/api/dashboard/knowledge-graph');
        const data = await res.json();
        const c = containerRef.current;
        if (c) { sizeRef.current = { w: c.clientWidth, h: c.clientHeight }; buildLayout(data, c.clientWidth, c.clientHeight); }
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [buildLayout]);

  // ─── Animation Phases ───
  // 0-0.7s: root appears (bounce)
  // 0.7-2.2s: lines to EPS grow, EPS fade in
  // 2.2-4.2s: lines to projects grow, projects fade in (staggered)
  // 4.2-5.2s: vendor lines + nodes
  // 5.2s+: particles flow

  const drawFrame = useCallback((ts: number) => {
    const canvas = canvasRef.current;
    if (!canvas) { animRef.current = requestAnimationFrame(drawFrame); return; }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w, h } = sizeRef.current;
    if (!w) { animRef.current = requestAnimationFrame(drawFrame); return; }

    const t = ts / 1000 - startTimeRef.current;
    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    const particles = particlesRef.current;
    const scale = scaleRef.current;
    const pan = panRef.current;
    const dpr = window.devicePixelRatio || 1;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // ── Light theme background ──
    const bg = ctx.createRadialGradient(w * dpr / 2, h * dpr / 2, 0, w * dpr / 2, h * dpr / 2, w * dpr * 0.7);
    bg.addColorStop(0, '#f8fafb');
    bg.addColorStop(0.6, '#f0f4f6');
    bg.addColorStop(1, '#e8eef2');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Subtle dot grid
    ctx.fillStyle = 'rgba(0,0,0,0.04)';
    const gridSize = 36 * dpr;
    for (let gx = 0; gx < canvas.width; gx += gridSize) {
      for (let gy = 0; gy < canvas.height; gy += gridSize) {
        ctx.beginPath();
        ctx.arc(gx, gy, 0.8 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.save();
    ctx.translate((w / 2 + pan.x) * dpr, (h / 2 + pan.y) * dpr);
    ctx.scale(scale * dpr, scale * dpr);
    ctx.translate(-w / 2, -h / 2);

    // ── Edges with staged reveal + connector dots ──
    edges.forEach((edge, ei) => {
      const src = nodes[edge.src];
      const tgt = nodes[edge.tgt];
      if (!src || !tgt) return;

      let prog = 0;
      if (edge.level === 1) prog = clamp((t - 0.7) / 1.2, 0, 1);
      else if (edge.level === 2) prog = clamp((t - 2.2) / 1.5, 0, 1);
      else if (edge.level === 3) prog = clamp((t - 4.2) / 0.8, 0, 1);
      if (prog <= 0) return;

      const ep = easeOutCubic(prog);
      const ex = src.x + (tgt.x - src.x) * ep;
      const ey = src.y + (tgt.y - src.y) * ep;

      // Thin elegant line — golden for root links, subtle gray for others
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(ex, ey);
      if (edge.level === 1) {
        const grad = ctx.createLinearGradient(src.x, src.y, ex, ey);
        grad.addColorStop(0, 'rgba(200, 160, 60, 0.5)');
        grad.addColorStop(1, 'rgba(140, 120, 80, 0.25)');
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.4;
      } else {
        ctx.strokeStyle = `rgba(120, 120, 140, ${edge.level === 2 ? 0.2 : 0.12})`;
        ctx.lineWidth = edge.level === 2 ? 0.8 : 0.5;
      }
      ctx.stroke();

      // Small connector dot at midpoint (like numbered dots in reference)
      if (prog >= 1 && edge.level <= 2) {
        const mx = (src.x + tgt.x) / 2;
        const my = (src.y + tgt.y) / 2;
        ctx.beginPath();
        ctx.arc(mx, my, edge.level === 1 ? 3.5 : 2.5, 0, Math.PI * 2);
        ctx.fillStyle = edge.level === 1 ? 'rgba(200,160,60,0.35)' : 'rgba(120,120,140,0.2)';
        ctx.fill();
      }
    });

    // ── Particles (after reveal) — subtle on light bg ──
    if (t > 5.2) {
      const pAlpha = clamp((t - 5.2) / 1.5, 0, 1);
      particles.forEach(p => {
        const edge = edges[p.edgeIdx];
        if (!edge || edge.level > 2) return; // only on root→EPS and EPS→project lines
        const src = nodes[edge.src], tgt = nodes[edge.tgt];
        if (!src || !tgt) return;
        p.t += p.speed;
        if (p.t > 1) p.t = 0;
        const px = src.x + (tgt.x - src.x) * p.t;
        const py = src.y + (tgt.y - src.y) * p.t;

        // Soft warm glow
        const gl = ctx.createRadialGradient(px, py, 0, px, py, p.size * 3);
        gl.addColorStop(0, `rgba(190,150,50,${0.3 * pAlpha})`);
        gl.addColorStop(1, 'rgba(190,150,50,0)');
        ctx.fillStyle = gl;
        ctx.fillRect(px - p.size * 3, py - p.size * 3, p.size * 6, p.size * 6);

        ctx.beginPath();
        ctx.arc(px, py, p.size * 0.8, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(170,130,40,${0.5 * pAlpha})`;
        ctx.fill();
      });
    }

    // ── Nodes with staged reveal ──
    nodes.forEach(node => {
      let alpha = 0, sc = 1;
      if (node.level === 0) {
        alpha = clamp(t / 0.5, 0, 1);
        sc = 0.2 + 0.8 * easeOutBack(clamp(t / 0.7, 0, 1));
      } else if (node.level === 1) {
        alpha = clamp((t - 1.5) / 0.5, 0, 1);
        sc = 0.5 + 0.5 * easeOutCubic(clamp((t - 1.5) / 0.5, 0, 1));
      } else if (node.level === 2) {
        alpha = clamp((t - 3.2) / 0.5, 0, 1);
        sc = 0.5 + 0.5 * easeOutCubic(clamp((t - 3.2) / 0.5, 0, 1));
      } else {
        alpha = clamp((t - 4.8) / 0.4, 0, 1);
      }
      if (alpha <= 0) return;
      drawNode(ctx, node, alpha, sc, t);
    });

    ctx.restore();
    animRef.current = requestAnimationFrame(drawFrame);
  }, []);

  useEffect(() => {
    if (!loading && nodesRef.current.length > 0) animRef.current = requestAnimationFrame(drawFrame);
    return () => cancelAnimationFrame(animRef.current);
  }, [loading, drawFrame]);

  // Resize
  useEffect(() => {
    const c = containerRef.current, cv = canvasRef.current;
    if (!c || !cv) return;
    const obs = new ResizeObserver(entries => {
      for (const e of entries) {
        const { width: cw, height: ch } = e.contentRect;
        const dpr = window.devicePixelRatio || 1;
        cv.width = cw * dpr; cv.height = ch * dpr;
        cv.style.width = `${cw}px`; cv.style.height = `${ch}px`;
        sizeRef.current = { w: cw, h: ch };
      }
    });
    obs.observe(c);
    return () => obs.disconnect();
  }, []);

  // Mouse
  const getNodeAt = useCallback((cx: number, cy: number): GNode | null => {
    const cv = canvasRef.current; if (!cv) return null;
    const rect = cv.getBoundingClientRect();
    const { w, h } = sizeRef.current;
    const s = scaleRef.current, p = panRef.current;
    const mx = (cx - rect.left - w / 2 - p.x) / s + w / 2;
    const my = (cy - rect.top - h / 2 - p.y) / s + h / 2;
    for (const n of nodesRef.current) {
      if ((mx - n.x) ** 2 + (my - n.y) ** 2 < (n.radius + 12) ** 2) return n;
    }
    return null;
  }, []);

  const onClick = useCallback((e: React.MouseEvent) => setSelectedNode(getNodeAt(e.clientX, e.clientY)), [getNodeAt]);
  const onDown = useCallback((e: React.MouseEvent) => { dragRef.current = { on: true, lx: e.clientX, ly: e.clientY }; }, []);
  const onMove = useCallback((e: React.MouseEvent) => {
    const d = dragRef.current;
    if (d.on) { panRef.current.x += e.clientX - d.lx; panRef.current.y += e.clientY - d.ly; d.lx = e.clientX; d.ly = e.clientY; }
    const cv = canvasRef.current;
    if (cv) cv.style.cursor = getNodeAt(e.clientX, e.clientY) ? 'pointer' : (d.on ? 'grabbing' : 'grab');
  }, [getNodeAt]);
  const onUp = useCallback(() => { dragRef.current.on = false; }, []);
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      scaleRef.current = Math.max(0.3, Math.min(3, scaleRef.current * (e.deltaY > 0 ? 0.9 : 1.1)));
    };
    cv.addEventListener('wheel', handleWheel, { passive: false });
    return () => cv.removeEventListener('wheel', handleWheel);
  }, []);

  const zoom = (d: 'in' | 'out') => { scaleRef.current = Math.max(0.3, Math.min(3, scaleRef.current * (d === 'in' ? 1.3 : 0.7))); };
  const reset = () => { scaleRef.current = 1; panRef.current = { x: 0, y: 0 }; setSelectedNode(null); };

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] w-full rounded-2xl border border-border overflow-hidden bg-background shadow-xl relative">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-muted/40 z-20 relative">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
            <Network className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-foreground tracking-wide">AKASHA KNOWLEDGE GRAPH</h2>
            <p className="text-[10px] text-muted-foreground font-mono tracking-widest">{stats.n} entities · {stats.e} connections</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => zoom('in')} className="p-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><ZoomIn className="w-4 h-4" /></button>
          <button onClick={() => zoom('out')} className="p-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><ZoomOut className="w-4 h-4" /></button>
          <button onClick={reset} className="p-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"><RotateCcw className="w-4 h-4" /></button>
        </div>
      </div>

      <div className="flex-1 relative flex overflow-hidden">
        <div ref={containerRef} className="flex-1 relative">
          {loading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 z-10">
              <div className="w-14 h-14 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center animate-pulse"><Network className="w-6 h-6 text-primary" /></div>
              <span className="text-xs text-muted-foreground">Mapping topology...</span>
            </div>
          )}
          <canvas ref={canvasRef} onClick={onClick} onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp} className="absolute inset-0 w-full h-full" />
        </div>

        {/* Rich Detail Panel (Floating Overlay) */}
        <AnimatePresence>
          {selectedNode && (
            <motion.div
              initial={{ x: 400, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 400, opacity: 0 }}
              transition={{ type: 'spring', bounce: 0.1, duration: 0.4 }}
              className="absolute right-4 top-4 bottom-4 w-80 bg-background/95 backdrop-blur-md border border-border rounded-xl shadow-2xl flex flex-col z-30 overflow-hidden"
              onWheel={(e) => e.stopPropagation()}
            >
              <div className="p-4 border-b border-border bg-muted/20">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: selectedNode.color }}>
                    {['Enterprise','EPS Region','Project','Project','Vendor'][selectedNode.category]}
                  </span>
                  <button onClick={() => setSelectedNode(null)} className="p-1 rounded-md hover:bg-muted text-muted-foreground transition-colors">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <h3 className="text-base font-bold text-foreground leading-tight">{selectedNode.name}</h3>
                {selectedNode.value && <p className="text-xs text-muted-foreground mt-1">{selectedNode.value}</p>}
                {selectedNode.spv && <p className="text-[10px] text-muted-foreground mt-1 font-mono">SPV: {selectedNode.spv}</p>}
              </div>
              
              <div className="flex-1 overflow-y-auto custom-scrollbar pointer-events-auto">
                {/* Health + Progress (Projects) */}
                {selectedNode.health && (
                  <div className="p-4 border-b border-border space-y-3">
                    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${selectedNode.health === 'delayed' ? 'bg-red-500/10' : 'bg-emerald-500/10'}`}>
                      <div className={`w-2.5 h-2.5 rounded-full animate-pulse ${selectedNode.health === 'delayed' ? 'bg-red-500' : 'bg-emerald-500'}`} />
                      <span className={`text-xs font-bold uppercase tracking-wider ${selectedNode.health === 'delayed' ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                        {selectedNode.health === 'delayed' ? 'Delayed' : 'On Track'}
                      </span>
                    </div>
                    {selectedNode.progress !== undefined && (
                      <div>
                        <div className="flex justify-between text-[11px] text-muted-foreground mb-1.5 font-medium">
                          <span>Progress</span>
                          <span className="font-mono">{selectedNode.progress}%</span>
                        </div>
                        <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                          <motion.div 
                            initial={{ width: 0 }} 
                            animate={{ width: `${selectedNode.progress}%` }} 
                            transition={{ duration: 0.8 }} 
                            className={`h-full rounded-full ${selectedNode.progress > 80 ? 'bg-emerald-500' : selectedNode.progress > 40 ? 'bg-blue-500' : 'bg-amber-500'}`} 
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* EPS Region stats */}
                {selectedNode.delayed !== undefined && (
                  <div className="p-4 border-b border-border">
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div className="bg-red-500/10 rounded-xl p-3 text-center border border-red-500/20">
                        <div className="text-xl font-bold text-red-600 dark:text-red-400">{selectedNode.delayed}</div>
                        <div className="text-[9px] text-red-600/80 dark:text-red-400/80 uppercase font-bold mt-0.5">Delayed</div>
                      </div>
                      <div className="bg-emerald-500/10 rounded-xl p-3 text-center border border-emerald-500/20">
                        <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{selectedNode.on_track}</div>
                        <div className="text-[9px] text-emerald-600/80 dark:text-emerald-400/80 uppercase font-bold mt-0.5">On Track</div>
                      </div>
                    </div>
                    
                    {/* Projects List within EPS */}
                    {selectedNode.projects_list && selectedNode.projects_list.length > 0 && (
                      <div className="mt-4">
                        <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Projects in Region ({selectedNode.projects_list.length})</h4>
                        <div className="space-y-2">
                          {selectedNode.projects_list.map((proj: any) => (
                            <div key={proj.id} className="p-2.5 bg-muted/30 rounded-lg border border-border flex justify-between items-center group hover:bg-muted/50 transition-colors">
                              <div className="flex-1 min-w-0 pr-3">
                                <div className="text-xs font-semibold text-foreground truncate" title={proj.name}>{proj.name}</div>
                                <div className="text-[10px] text-muted-foreground mt-0.5 font-mono">{proj.capacity} MW</div>
                              </div>
                              <div className={`px-2 py-1 rounded-md text-[10px] font-bold shrink-0 ${proj.health === 'delayed' ? 'bg-red-500/15 text-red-600 dark:text-red-400' : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'}`}>
                                {proj.progress}%
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* P6 Schedule Section */}
                {selectedNode.p6 && <DetailSection icon={<Calendar className="w-4 h-4" />} title="P6 Schedule" color="#3B82F6">
                  <DetailRow label="Status" value={selectedNode.p6.status} />
                  <DetailRow label="Start Date" value={selectedNode.p6.start_date || '—'} />
                  <DetailRow label="Finish Date" value={selectedNode.p6.finish_date || '—'} />
                  <DetailRow label="Planned Finish" value={selectedNode.p6.planned_finish || '—'} />
                  <DetailRow label="Variance" value={`${selectedNode.p6.variance_days} days`} highlight={selectedNode.p6.variance_days < 0 ? 'red' : 'green'} />
                  <DetailRow label="Duration %" value={`${selectedNode.p6.duration_pct}%`} />
                  <DetailRow label="Schedule %" value={`${selectedNode.p6.schedule_pct}%`} />
                </DetailSection>}

                {/* SAP Material Section */}
                {selectedNode.sap && <DetailSection icon={<Package className="w-4 h-4" />} title="SAP Material Tracking" color="#F59E0B">
                  <DetailRow label="Plant Code" value={selectedNode.sap.plant_code} />
                  <div className="grid grid-cols-2 gap-2 my-3">
                    <MiniCard label="POs" value={selectedNode.sap.po_count} sub={`₹${selectedNode.sap.po_total_cr} Cr`} />
                    <MiniCard label="PO MW" value={`${selectedNode.sap.po_mw}`} sub="ordered" />
                    <MiniCard label="Requirements" value={selectedNode.sap.requirement_count} sub={`${selectedNode.sap.requirement_mw} MW`} />
                    <MiniCard label="Inventory" value={selectedNode.sap.inventory_items} sub="items" />
                  </div>
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 mb-3">
                    <Truck className="w-4 h-4 text-amber-600 dark:text-amber-500" />
                    <span className="text-xs text-amber-700 dark:text-amber-400 font-semibold">{selectedNode.sap.in_transit_count} in transit · {selectedNode.sap.in_transit_mw} MW</span>
                  </div>
                  {selectedNode.sap.top_vendors?.length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold mb-2">Top Vendors</div>
                      {selectedNode.sap.top_vendors.map((v: any, i: number) => (
                        <div key={i} className="flex justify-between items-center py-1.5 border-b border-border/50 last:border-0">
                          <span className="text-xs text-foreground font-medium truncate pr-2">{v.name}</span>
                          <span className="text-[11px] text-muted-foreground font-mono shrink-0">₹{v.value_cr} Cr</span>
                        </div>
                      ))}
                    </div>
                  )}
                </DetailSection>}

                {/* Transmission Section */}
                {selectedNode.tc && <DetailSection icon={<Zap className="w-4 h-4" />} title="Transmission Network" color="#10B981">
                  <DetailRow label="Region" value={selectedNode.tc.region} />
                  <DetailRow label="Substations" value={selectedNode.tc.total_substations} />
                  <DetailRow label="Lines" value={selectedNode.tc.total_lines} />
                  
                  {selectedNode.tc.substations?.length > 0 && (
                    <div className="mt-3 text-[10px]">
                      <span className="font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Substations:</span>
                      <span className="text-foreground leading-relaxed">{selectedNode.tc.substations.join(', ')}</span>
                    </div>
                  )}
                  
                  {selectedNode.tc.lines?.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <div className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold border-b border-border/50 pb-1.5 mb-2">Lines Progress</div>
                      {selectedNode.tc.lines.map((l: any, i: number) => {
                        const isDone = ['completed', 'charged'].includes(l.status?.toLowerCase());
                        return (
                          <div key={i} className={`border rounded-lg p-2.5 text-[10px] space-y-1.5 ${isDone ? 'bg-emerald-500/5 border-emerald-500/10' : 'bg-amber-500/5 border-amber-500/10'}`}>
                            <div className="font-bold text-foreground flex justify-between items-start gap-2 leading-tight">
                              <span>{l.from || '?'} <span className="text-muted-foreground font-normal mx-0.5">→</span> {l.to || '?'}</span>
                              <span className={`shrink-0 ${isDone ? 'text-emerald-500' : 'text-amber-500'}`}>{l.status || 'Ongoing'}</span>
                            </div>
                            <div className="grid grid-cols-3 gap-1 pt-1 border-t border-border/30 text-muted-foreground">
                              <div>Fdn: <span className="font-mono text-foreground font-medium">{l.foundation || 0}%</span></div>
                              <div>Erec: <span className="font-mono text-foreground font-medium">{l.erection || 0}%</span></div>
                              <div>Str: <span className="font-mono text-foreground font-medium">{l.stringing || 0}%</span></div>
                            </div>
                            {l.expected_date && <div className="text-muted-foreground pt-0.5 italic">Expected: {l.expected_date.split(' ')[0]}</div>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </DetailSection>}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-4 bg-card/80 backdrop-blur-md px-4 py-2 rounded-lg border border-border shadow-sm">
        {[
          { c: STYLE.root.fill, l: 'Akasha' }, { c: STYLE.eps.fill, l: 'EPS Region' },
          { c: STYLE.ok.fill, l: 'On Track' }, { c: STYLE.delayed.fill, l: 'Delayed' },
          { c: STYLE.vendor.fill, l: 'Vendor' }
        ].map(i => (
          <div key={i.l} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: i.c }} />
            <span className="text-[10px] text-muted-foreground font-medium">{i.l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function drawNode(ctx: CanvasRenderingContext2D, node: GNode, alpha: number, sc: number, time: number) {
  if (alpha <= 0) return;
  const { x, y, color, glowColor } = node;
  const r = node.radius * sc;
  ctx.globalAlpha = alpha;

  // Outer glow
  const glow = ctx.createRadialGradient(x, y, r * 0.3, x, y, r * 2.5);
  glow.addColorStop(0, glowColor);
  glow.addColorStop(1, 'transparent');
  ctx.fillStyle = glow;
  ctx.fillRect(x - r * 2.5, y - r * 2.5, r * 5, r * 5);

  // Root pulse
  if (node.level === 0) {
    const pulse = 0.5 + 0.5 * Math.sin(time * 1.8);
    const pg = ctx.createRadialGradient(x, y, r, x, y, r * 3.5);
    pg.addColorStop(0, `rgba(212,168,83,${0.1 * pulse})`);
    pg.addColorStop(1, 'transparent');
    ctx.fillStyle = pg;
    ctx.fillRect(x - r * 3.5, y - r * 3.5, r * 7, r * 7);
  }

  // 3D sphere
  const sp = ctx.createRadialGradient(x - r * 0.25, y - r * 0.3, r * 0.05, x, y, r);
  sp.addColorStop(0, '#ffffff');
  sp.addColorStop(0.2, lighten(color, 40));
  sp.addColorStop(0.55, color);
  sp.addColorStop(1, darken(color, 35));
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = sp; ctx.fill();

  // Shadow (light theme)
  ctx.beginPath(); ctx.arc(x, y + r * 0.3, r * 0.9, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0,0,0,0.04)'; ctx.fill();

  // Label
  const fs = node.level === 0 ? 13 : node.level === 1 ? 10 : 8;
  ctx.font = `${node.level <= 1 ? '600 ' : '400 '}${fs}px Adani, Inter, system-ui`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  const ly = y + r + 5;
  const label = node.name.length > 24 ? node.name.slice(0, 22) + '..' : node.name;

  // Text with outline for readability on light bg
  ctx.strokeStyle = 'rgba(255,255,255,0.8)';
  ctx.lineWidth = 3;
  ctx.lineJoin = 'round';
  ctx.strokeText(label, x, ly);
  ctx.fillStyle = node.labelColor;
  ctx.fillText(label, x, ly);

  // Sub-label
  if (node.level === 1 && node.value) {
    ctx.font = `8px Adani, Inter, system-ui`;
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 2;
    const sub = node.value.split('·')[0]?.trim() || '';
    ctx.strokeText(sub, x, ly + fs + 2);
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillText(sub, x, ly + fs + 2);
  }

  ctx.globalAlpha = 1;
}

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }
function easeOutCubic(t: number) { return 1 - (1 - t) ** 3; }
function easeOutBack(t: number) { const c = 1.7; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; }

function lighten(hex: string, pct: number): string {
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgb(${Math.min(255, (n >> 16) + Math.round(pct * 2.55))},${Math.min(255, ((n >> 8) & 0xff) + Math.round(pct * 2.55))},${Math.min(255, (n & 0xff) + Math.round(pct * 2.55))})`;
}
function darken(hex: string, pct: number): string {
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgb(${Math.max(0, (n >> 16) - Math.round(pct * 2.55))},${Math.max(0, ((n >> 8) & 0xff) - Math.round(pct * 2.55))},${Math.max(0, (n & 0xff) - Math.round(pct * 2.55))})`;
}

// ─── Detail Panel Sub-components ───

function DetailSection({ icon, title, color, children }: { icon: React.ReactNode; title: string; color: string; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(true);
  return (
    <div className="border-b border-border">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-4 py-3 hover:bg-muted/50 transition-colors">
        <div className="w-5 h-5 rounded flex items-center justify-center" style={{ backgroundColor: `${color}15`, color }}>{icon}</div>
        <span className="text-[11px] font-bold text-foreground flex-1 text-left">{title}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-3 space-y-1.5">{children}</div>}
    </div>
  );
}

function DetailRow({ label, value, highlight }: { label: string; value: any; highlight?: 'red' | 'green' }) {
  return (
    <div className="flex justify-between items-center py-0.5">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span className={`text-[10px] font-semibold font-mono ${
        highlight === 'red' ? 'text-red-600' : highlight === 'green' ? 'text-emerald-600' : 'text-foreground'
      }`}>{value}</span>
    </div>
  );
}

function MiniCard({ label, value, sub }: { label: string; value: any; sub: string }) {
  return (
    <div className="bg-muted/50 rounded-lg p-2 text-center border border-border/50">
      <div className="text-sm font-bold text-foreground">{value}</div>
      <div className="text-[8px] text-muted-foreground uppercase font-bold tracking-wider">{label}</div>
      <div className="text-[8px] text-muted-foreground">{sub}</div>
    </div>
  );
}
