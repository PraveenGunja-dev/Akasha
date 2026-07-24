import React, { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Network, X, RotateCcw, ChevronDown, ChevronRight, Calendar, Package, Zap, Building2, Truck, Search, Filter } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

interface GNode {
  id: string; project_id?: string; name: string; category: number; value?: string;
  health?: string; progress?: number; delayed?: number; on_track?: number;
  x: number; y: number; radius: number;
  targetX: number; targetY: number;
  color: string; glowColor: string; labelColor: string;
  level: number;
  childCount?: number;
  spv?: string; capacity?: number;
  p6?: any; sap?: any; tc?: any; projects_list?: any[];
  children?: GNode[];
  parent?: GNode;
  expanded: boolean;
  visible: boolean;
  alpha: number;
  mw_stats?: { total: number; cod: number; trial: number; };
}

interface GEdge { src: string; tgt: string; level: number; }
interface Particle { edgeIdx: number; t: number; speed: number; size: number; }

const STYLE = {
  root:      { fill: '#D4A853', glow: '#D4A85318', label: '#B45309' },
  portfolio: { fill: '#3B82F6', glow: '#3B82F618', label: '#2563EB' },
  eps:       { fill: '#7C3AED', glow: '#7C3AED18', label: '#6D28D9' },
  ok:        { fill: '#10B981', glow: '#10B98118', label: '#059669' },
  delayed:   { fill: '#EF4444', glow: '#EF444418', label: '#DC2626' },
  vendor:    { fill: '#F59E0B', glow: '#F59E0B18', label: '#D97706' },
};

function getStyle(cat: number, health?: string) {
  if (cat === 0) return STYLE.root;
  if (cat === 1) return STYLE.portfolio;
  if (cat === 2) return STYLE.eps;
  if (cat === 4 || health === 'delayed') return STYLE.delayed;
  if (cat === 5) return STYLE.vendor;
  return STYLE.ok;
}

function hexToRgba(hex: string, alpha: number) {
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 0xff}, ${n & 0xff}, ${alpha})`;
}

export default function KnowledgeGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef(0);
  const nodesMapRef = useRef<Map<string, GNode>>(new Map());
  const edgesRef = useRef<GEdge[]>([]);
  const particlesRef = useRef<Particle[]>([]);
  const startTimeRef = useRef(0);
  const scaleRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const dragRef = useRef({ on: false, lx: 0, ly: 0 });
  const sizeRef = useRef({ w: 0, h: 0 });
  const rootDataRef = useRef<any>(null);

  const [selectedNode, setSelectedNode] = useState<GNode | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ n: 0, e: 0 });
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');

  // New State
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  const processData = useCallback(() => {
    const data = rootDataRef.current;
    if (!data) return;
    const raw = data.nodes || [];
    const rawLinks = data.links || [];
    
    // 1. Maintain or Create Nodes
    const nodeMap = nodesMapRef.current;
    
    // Add new nodes, update existing
    raw.forEach((n: any) => {
       const existing = nodeMap.get(n.id);
       const s = getStyle(n.category, n.health);
       if (existing) {
           existing.expanded = expandedNodes.has(n.id);
           existing.children = [];
           existing.parent = undefined;
       } else {
           nodeMap.set(n.id, {
             ...n,
             radius: n.category === 0 ? 36 : n.category === 1 ? 24 : n.category === 4 ? 6 : 8,
             color: s.fill, glowColor: s.glow, labelColor: s.label,
             level: n.category,
             x: 0, y: 0, targetX: 0, targetY: 0,
             children: [], expanded: expandedNodes.has(n.id), visible: false, alpha: 0
           });
       }
    });

    // 2. Build Tree
    rawLinks.forEach((l: any) => {
       const src = nodeMap.get(l.source);
       const tgt = nodeMap.get(l.target);
       if (src && tgt && src.category < tgt.category) { // Avoid cycles, enforce hierarchy
           src.children!.push(tgt);
           tgt.parent = src;
       }
    });
    
    // Artificially link Root to all EPS clusters (category 1) if not linked, and always expand Root
    const rootNodes = Array.from(nodeMap.values()).filter(n => n.category === 0);
    const epsNodes = Array.from(nodeMap.values()).filter(n => n.category === 1);
    
    if (rootNodes[0]) {
        rootNodes[0].expanded = true; // Always open Root
        epsNodes.forEach(eps => {
            if (!eps.parent) {
                rootNodes[0].children!.push(eps);
                eps.parent = rootNodes[0];
            }
        });
    }
    
    // Auto-expand for search
    if (searchQuery.trim().length > 1) {
        const query = searchQuery.toLowerCase();
        nodeMap.forEach(n => {
            if (n.name.toLowerCase().includes(query)) {
                let p = n.parent;
                while (p) { p.expanded = true; p = p.parent; }
            }
        });
    }

    // 3. Layout (Horizontal Tree)
    const edges: GEdge[] = [];
    let currentY = 0;
    const horizontalSpacing = 340;
    const verticalSpacing = 70;
    const { w, h } = sizeRef.current;

    nodeMap.forEach(n => n.visible = false);

    function traverse(node: GNode, depth: number) {
        node.targetX = depth * horizontalSpacing;
        node.level = depth;
        node.visible = true;
        
        // Dynamic EPS size (now category 2)
        if (node.category === 2 && node.children) {
            node.radius = Math.max(16, Math.min(26, 14 + node.children.length * 1.2));
        }
        
        if (node.expanded && node.children && node.children.length > 0) {
            let childYSum = 0;
            node.children.forEach(child => {
                traverse(child, depth + 1);
                childYSum += child.targetY;
                edges.push({ src: node.id, tgt: child.id, level: depth + 1 });
            });
            node.targetY = childYSum / node.children.length;
        } else {
            node.targetY = currentY;
            currentY += verticalSpacing;
        }
    }
    
    if (rootNodes[0]) traverse(rootNodes[0], 0);
    
    // Center vertically and anchor horizontally to the left
    const yOffset = (currentY - verticalSpacing) / 2;
    const centerY = h / 2;

    // Set targets for all nodes
    nodeMap.forEach(n => { 
        if (n.visible) {
            n.targetY = n.targetY - yOffset + centerY;
            n.targetX = n.targetX + 140; // 140px from left edge
            if (n.x === 0 && n.y === 0) {
                // If it's a new node popping in, start it at parent's position
                n.x = n.parent ? n.parent.targetX : n.targetX;
                n.y = n.parent ? n.parent.targetY : n.targetY;
            }
        } else {
            // collapsed nodes shrink into their closest visible ancestor
            let p = n.parent;
            while (p && !p.visible) p = p.parent;
            if (p) {
                n.targetX = p.targetX;
                n.targetY = p.targetY;
            }
        }
    });

    edgesRef.current = edges;
    
    // Particles
    const particles: Particle[] = [];
    edges.forEach((_, i) => {
      const count = 1 + Math.floor(Math.random() * 2);
      for (let j = 0; j < count; j++)
        particles.push({ edgeIdx: i, t: Math.random(), speed: 0.002 + Math.random() * 0.003, size: 1 + Math.random() * 1.5 });
    });
    particlesRef.current = particles;

    setStats({ n: Array.from(nodeMap.values()).filter(n=>n.visible).length, e: edges.length });
  }, [expandedNodes, searchQuery]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const url = portfolio ? `/akasha/api/dashboard/knowledge-graph?portfolio=${encodeURIComponent(portfolio)}` : '/akasha/api/dashboard/knowledge-graph';
        const res = await fetch(url);
        const data = await res.json();
        rootDataRef.current = data;
        const c = containerRef.current;
        if (c) { 
            sizeRef.current = { w: c.clientWidth, h: c.clientHeight }; 
            // Reset state on new data
            setExpandedNodes(new Set());
            nodesMapRef.current = new Map();
            processData(); 
            startTimeRef.current = performance.now() / 1000;
        }
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [portfolio]); // Removed processData from dependencies to fix infinite loop

  // Re-process when expanded nodes or search changes
  useEffect(() => {
     if (rootDataRef.current) processData();
  }, [expandedNodes, searchQuery, processData]);

  // ─── Animation Loop ───
  const drawFrame = useCallback((ts: number) => {
    const canvas = canvasRef.current;
    if (!canvas) { animRef.current = requestAnimationFrame(drawFrame); return; }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w, h } = sizeRef.current;
    if (!w) { animRef.current = requestAnimationFrame(drawFrame); return; }

    const t = ts / 1000 - startTimeRef.current;
    const nodeMap = nodesMapRef.current;
    const edges = edgesRef.current;
    const particles = particlesRef.current;
    const scale = scaleRef.current;
    const pan = panRef.current;
    const dpr = window.devicePixelRatio || 1;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Subtle dot grid
    ctx.fillStyle = 'rgba(0,0,0,0.03)';
    const gridSize = 36 * dpr;
    for (let gx = (pan.x * scale * dpr) % gridSize; gx < canvas.width; gx += gridSize) {
      for (let gy = (pan.y * scale * dpr) % gridSize; gy < canvas.height; gy += gridSize) {
        ctx.beginPath();
        ctx.arc(gx, gy, 0.8 * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.save();
    ctx.translate((w / 2 + pan.x) * dpr, (h / 2 + pan.y) * dpr);
    ctx.scale(dpr, dpr); // scale is fixed to dpr, no dynamic zooming
    ctx.translate(-w / 2, -h / 2);

    // Physics Lerp & Alpha Update
    nodeMap.forEach(node => {
      node.x += (node.targetX - node.x) * 0.12;
      node.y += (node.targetY - node.y) * 0.12;
      if (node.visible) {
          node.alpha = Math.min(1, node.alpha + 0.05);
      } else {
          node.alpha = Math.max(0, node.alpha - 0.1);
      }
    });

    // Draw Edges (n8n Bezier Style)
    edges.forEach((edge, ei) => {
      const src = nodeMap.get(edge.src);
      const tgt = nodeMap.get(edge.tgt);
      if (!src || !tgt) return;
      if (src.alpha <= 0.01 && tgt.alpha <= 0.01) return;

      const pAlpha = Math.min(src.alpha, tgt.alpha);
      
      const startX = src.x + src.radius;
      const endX = tgt.x - tgt.radius;
      
      ctx.beginPath();
      ctx.moveTo(startX, src.y);
      const cpDist = Math.max(40, Math.abs(endX - startX) * 0.5);
      ctx.bezierCurveTo(startX + cpDist, src.y, endX - cpDist, tgt.y, endX, tgt.y);
      
      const grad = ctx.createLinearGradient(startX, src.y, endX, tgt.y);
      grad.addColorStop(0, hexToRgba(src.color, pAlpha * 0.5));
      grad.addColorStop(1, hexToRgba(tgt.color, pAlpha * 0.3));
      ctx.strokeStyle = grad;
      ctx.lineWidth = edge.level === 1 ? 2.5 : 1.5;
      ctx.stroke();
    });

    // Particles along bezier
    particles.forEach(p => {
        const edge = edges[p.edgeIdx];
        if (!edge) return;
        const src = nodeMap.get(edge.src), tgt = nodeMap.get(edge.tgt);
        if (!src || !tgt) return;
        const pAlpha = Math.min(src.alpha, tgt.alpha);
        if (pAlpha <= 0.01) return;

        p.t += p.speed;
        if (p.t > 1) p.t = 0;
        
        // Bezier interpolation
        const u = 1 - p.t;
        const tt = p.t * p.t;
        const uu = u * u;
        const uuu = uu * u;
        const ttt = tt * p.t;
        
        const startX = src.x + src.radius;
        const endX = tgt.x - tgt.radius;
        
        const cpDist = Math.max(40, Math.abs(endX - startX) * 0.5);
        const p0x = startX, p0y = src.y;
        const p1x = startX + cpDist, p1y = src.y;
        const p2x = endX - cpDist, p2y = tgt.y;
        const p3x = endX, p3y = tgt.y;
        
        const px = uuu * p0x + 3 * uu * p.t * p1x + 3 * u * tt * p2x + ttt * p3x;
        const py = uuu * p0y + 3 * uu * p.t * p1y + 3 * u * tt * p2y + ttt * p3y;

        const gl = ctx.createRadialGradient(px, py, 0, px, py, p.size * 3);
        gl.addColorStop(0, `rgba(255,255,255,${0.8 * pAlpha})`);
        gl.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = gl;
        ctx.fillRect(px - p.size * 3, py - p.size * 3, p.size * 6, p.size * 6);
    });

    // Draw Nodes
    const query = searchQuery.toLowerCase();
    nodeMap.forEach(node => {
      if (node.alpha <= 0.01) return;
      const isHovered = hoveredNodeId === node.id;
      const isSearchMatch = query.length > 1 && node.name.toLowerCase().includes(query);
      drawNode(ctx, node, t, isHovered, isSearchMatch);
      
      // Expand Icon indicator for nodes with children
      if (node.children && node.children.length > 0 && node.visible && node.alpha > 0.8) {
          ctx.beginPath();
          ctx.arc(node.x + node.radius, node.y, 6, 0, Math.PI * 2);
          ctx.fillStyle = node.expanded ? '#f1f5f9' : node.color;
          ctx.fill();
          ctx.strokeStyle = '#cbd5e1';
          ctx.lineWidth = 1;
          ctx.stroke();
          
          ctx.fillStyle = node.expanded ? '#64748b' : '#ffffff';
          ctx.font = 'bold 8px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(node.expanded ? '-' : '+', node.x + node.radius, node.y + 0.5);
      }
    });

    ctx.restore();
    animRef.current = requestAnimationFrame(drawFrame);
  }, [hoveredNodeId, searchQuery]);

  useEffect(() => {
    if (!loading) animRef.current = requestAnimationFrame(drawFrame);
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

  // Mouse Interactivity
  const getNodeAt = useCallback((cx: number, cy: number): GNode | null => {
    const cv = canvasRef.current; if (!cv) return null;
    const rect = cv.getBoundingClientRect();
    const { w, h } = sizeRef.current;
    const p = panRef.current;
    // Scale is strictly 1 now
    const mx = (cx - rect.left - w / 2 - p.x) + w / 2;
    const my = (cy - rect.top - h / 2 - p.y) + h / 2;
    
    // Reverse iterate to click top-most nodes first
    const nodes = Array.from(nodesMapRef.current.values()).filter(n => n.visible);
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if ((mx - n.x) ** 2 + (my - n.y) ** 2 < (n.radius + 12) ** 2) return n;
    }
    return null;
  }, []);

  const onClick = useCallback((e: React.MouseEvent) => {
      const node = getNodeAt(e.clientX, e.clientY);
      if (node) {
          if (node.children && node.children.length > 0) {
              setExpandedNodes(prev => {
                  const next = new Set(prev);
                  if (next.has(node.id)) next.delete(node.id);
                  else next.add(node.id);
                  return next;
              });
          }
          if (node.category > 0) {
              setSelectedNode(node);
          }
      } else {
          setSelectedNode(null);
      }
  }, [getNodeAt]);
  
  const onDown = useCallback((e: React.MouseEvent) => { dragRef.current = { on: true, lx: e.clientX, ly: e.clientY }; }, []);
  const onMove = useCallback((e: React.MouseEvent) => {
    const d = dragRef.current;
    if (d.on) { panRef.current.x += e.clientX - d.lx; panRef.current.y += e.clientY - d.ly; d.lx = e.clientX; d.ly = e.clientY; }
    const cv = canvasRef.current;
    const node = getNodeAt(e.clientX, e.clientY);
    if (cv) cv.style.cursor = node ? 'pointer' : (d.on ? 'grabbing' : 'grab');
    setHoveredNodeId(node ? node.id : null);
  }, [getNodeAt]);
  const onUp = useCallback(() => { dragRef.current.on = false; }, []);
  
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      panRef.current.x -= e.deltaX;
      panRef.current.y -= e.deltaY;
    };
    cv.addEventListener('wheel', handleWheel, { passive: false });
    return () => cv.removeEventListener('wheel', handleWheel);
  }, []);

  const reset = () => { panRef.current = { x: 0, y: 0 }; setSelectedNode(null); setExpandedNodes(new Set()); setSearchQuery(''); };

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] w-full relative">

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
              <div className="p-4 border-b border-border bg-muted">
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
                    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${selectedNode.health === 'delayed' ? 'bg-destructive/100/10' : 'bg-success/100/10'}`}>
                      <div className={`w-2.5 h-2.5 rounded-full animate-pulse ${selectedNode.health === 'delayed' ? 'bg-destructive/100' : 'bg-success/100'}`} />
                      <span className={`text-xs font-bold uppercase tracking-wider ${selectedNode.health === 'delayed' ? 'text-destructive dark:text-destructive' : 'text-success dark:text-success'}`}>
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
                            className={`h-full rounded-full ${selectedNode.progress > 80 ? 'bg-success/100' : selectedNode.progress > 40 ? 'bg-primary/100' : 'bg-warning/100'}`} 
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
                      <div className="bg-destructive/100/10 rounded-xl p-3 text-center border border-destructive/20">
                        <div className="text-xl font-bold text-destructive dark:text-destructive">{selectedNode.delayed}</div>
                        <div className="text-[9px] text-destructive/80 dark:text-destructive/80 uppercase font-bold mt-0.5">Delayed</div>
                      </div>
                      <div className="bg-success/100/10 rounded-xl p-3 text-center border border-success/20">
                        <div className="text-xl font-bold text-success dark:text-success">{selectedNode.on_track}</div>
                        <div className="text-[9px] text-success/80 dark:text-success/80 uppercase font-bold mt-0.5">On Track</div>
                      </div>
                    </div>
                    
                    {/* Projects List within EPS */}
                    {selectedNode.projects_list && selectedNode.projects_list.length > 0 && (
                      <div className="mt-4">
                        <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Projects in Region ({selectedNode.projects_list.length})</h4>
                        <div className="space-y-2">
                          {selectedNode.projects_list.map((proj: any) => (
                            <div key={proj.id} className="p-2.5 bg-muted rounded-lg border border-border flex justify-between items-center group hover:bg-muted transition-colors">
                              <div className="flex-1 min-w-0 pr-3">
                                <div className="text-xs font-semibold text-foreground truncate" title={proj.name}>{proj.name}</div>
                                <div className="text-[10px] text-muted-foreground mt-0.5 font-mono">{proj.capacity} MW</div>
                              </div>
                              <div className={`px-2 py-1 rounded-md text-[10px] font-bold shrink-0 ${proj.health === 'delayed' ? 'bg-destructive/100/15 text-destructive dark:text-destructive' : 'bg-success/100/15 text-success dark:text-success'}`}>
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
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-warning/100/10 border border-warning/20 mb-3">
                    <Truck className="w-4 h-4 text-warning dark:text-warning" />
                    <span className="text-xs text-warning dark:text-warning font-semibold">{selectedNode.sap.in_transit_count} in transit · {selectedNode.sap.in_transit_mw} MW</span>
                  </div>
                  {selectedNode.sap.top_vendors?.length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold mb-2">Top Vendors</div>
                      {selectedNode.sap.top_vendors.map((v: any, i: number) => (
                        <div key={i} className="flex justify-between items-center py-1.5 border-b border-border last:border-0">
                          <span className="text-xs text-foreground font-medium truncate pr-2">{v.name}</span>
                          <span className="text-[11px] text-muted-foreground font-mono shrink-0">₹{v.value_cr} Cr</span>
                        </div>
                      ))}
                    </div>
                  )}
                </DetailSection>}

                {/* Transmission Linkage Section */}
                {selectedNode.tc && selectedNode.tc.total_lines > 0 && (
                  <DetailSection title="Transmission Linkage" icon={<Network className="w-4 h-4" />} color="#8B5CF6">
                    
                    {/* Live Transmission Portal Link */}
                    <div className="flex justify-end mb-2">
                      <a
                        href={`https://adani.unada.in/transmission/v1/dashboard/khavda/commissioning-team?project=${encodeURIComponent(selectedNode.project_id || '')}&email=c7lj9OK6uzRLjiZLxS84y0QthSsZe7POcrGs-DIVaA0pmSPD9rlCGg2-Cg&pass=bFLZzcL7tsx1pZUJBqCXnMMkKQySqhmUDczHBCCX63aLNJ69`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground text-[9px] uppercase tracking-wider px-2.5 py-1.5 rounded font-bold transition-all w-fit group"
                      >
                        Open Portal <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                      </a>
                    </div>

                    <div className="grid grid-cols-3 gap-2 my-2 mb-3">
                      <div className="bg-muted border border-border rounded flex flex-col items-center justify-center py-2">
                        <span className="text-sm font-bold text-foreground">{selectedNode.tc.total_lines}</span>
                        <span className="text-[9px] uppercase font-bold text-muted-foreground">Total</span>
                      </div>
                      <div className="bg-success/100/10 border border-success/20 rounded flex flex-col items-center justify-center py-2">
                        <span className="text-sm font-bold text-success dark:text-success">{selectedNode.tc.charged_lines}</span>
                        <span className="text-[9px] uppercase font-bold text-success dark:text-success">Charged</span>
                      </div>
                      <div className="bg-destructive/100/10 border border-destructive/20 rounded flex flex-col items-center justify-center py-2">
                        <span className="text-sm font-bold text-destructive dark:text-destructive">{selectedNode.tc.delayed_lines}</span>
                        <span className="text-[9px] uppercase font-bold text-destructive dark:text-destructive">Delayed</span>
                      </div>
                    </div>
                    {selectedNode.tc.lines?.length > 0 && (
                      <div className="flex flex-col gap-1.5 max-h-[250px] overflow-y-auto scrollbar-thin">
                        {selectedNode.tc.lines.map((line: any, idx: number) => {
                          const norm = line.normalized_status || 'in_progress';
                          const badgeColor = norm === 'charged' ? 'bg-success/100/10 text-success dark:text-success' :
                            norm === 'delayed' ? 'bg-destructive/100/10 text-destructive dark:text-destructive' :
                            'bg-primary/100/10 text-primary dark:text-primary';
                          const displayStatus = norm === 'charged' ? 'CHARGED' : norm === 'delayed' ? 'DELAYED' : 'IN PROGRESS';

                          return (
                            <div key={idx} className="flex flex-col bg-background/50 px-2 py-1.5 rounded border border-border text-xs">
                              <div className="flex justify-between items-center pb-1">
                                <span className="text-foreground truncate pr-2" title={line.name}>{line.name}</span>
                                <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded ${badgeColor}`}>
                                  {displayStatus}
                                </span>
                              </div>
                              
                              {(line.foundation || line.erection || line.stringing) && (
                                <div className="grid grid-cols-3 gap-2 pt-1.5 border-t border-border/30 text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
                                  <div>Fdn: <span className="font-mono text-foreground font-bold ml-1">{line.foundation?.split('/')[0] || 0}</span></div>
                                  <div>Erec: <span className="font-mono text-foreground font-bold ml-1">{line.erection?.split('/')[0] || 0}</span></div>
                                  <div>Str: <span className="font-mono text-foreground font-bold ml-1">{line.stringing?.split('/')[0] || 0}</span></div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </DetailSection>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Legend */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-2.5 bg-white/90 backdrop-blur-md px-4 py-3 rounded-lg border border-border shadow-sm">
        <div className="flex items-center gap-4">
          {[
            { c: STYLE.root.fill, l: 'Enterprise' }, { c: STYLE.portfolio.fill, l: 'Portfolio' }, { c: STYLE.eps.fill, l: 'EPS Region' },
            { c: STYLE.ok.fill, l: 'Project (On Track)' }, { c: STYLE.delayed.fill, l: 'Project (Delayed)' },
            { c: STYLE.vendor.fill, l: 'Vendor' }
          ].map(i => (
            <div key={i.l} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: i.c }} />
              <span className="text-[10px] text-muted-foreground font-medium">{i.l}</span>
            </div>
          ))}
        </div>
        
        <div className="flex items-center gap-6 pt-2 border-t border-border/50">
          <div className="flex items-center gap-2">
             <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Stats Format:</span>
             <span className="text-[10px] font-mono"><span className="text-primary font-bold">Total MW</span> <span className="text-muted-foreground">/</span> <span className="text-success font-bold">COD</span> <span className="text-muted-foreground">/</span> <span className="text-warning font-bold">Trial</span></span>
          </div>
          <div className="flex items-center gap-2">
             <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest">Project Maps:</span>
             <div className="flex gap-2 items-center">
               <span className="text-[10px] font-bold text-primary">● P6 Schedule</span>
               <span className="text-[10px] font-bold text-pink-500">● SAP Material</span>
               <span className="text-[10px] font-bold text-destructive">● TC Network</span>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function drawNode(ctx: CanvasRenderingContext2D, node: GNode, time: number, hovered: boolean, isSearchMatch: boolean) {
  ctx.globalAlpha = node.alpha;
  const { x, y, color, radius } = node;
  const r = radius;

  // Delayed Pulse
  if (node.health === 'delayed') {
    const pulse = 0.5 + 0.5 * Math.sin(time * 3);
    ctx.beginPath();
    ctx.arc(x, y, r + 4 + pulse * 6, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(239, 68, 68, ${0.15 * pulse})`;
    ctx.fill();
    ctx.strokeStyle = `rgba(239, 68, 68, ${0.4 * pulse})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  if (isSearchMatch) {
    ctx.beginPath();
    ctx.arc(x, y, r + 10, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(59, 130, 246, 0.2)`;
    ctx.fill();
    ctx.strokeStyle = `rgba(59, 130, 246, 0.8)`;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // Premium Node Rendering
  ctx.save();
  
  // Drop Shadow
  ctx.shadowColor = 'rgba(0, 0, 0, 0.15)';
  ctx.shadowBlur = 12;
  ctx.shadowOffsetY = 4;
  
  // Base Circle
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  
  const isDark = document.documentElement.classList.contains('dark');
  
  if (node.category === 3 || node.category === 4) {
    const healthColor = node.health === 'delayed' ? '#EF4444' : '#10B981';
    
    // Just draw the health color for the dot (progress)
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = healthColor;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.stroke();

    if (hovered || isSearchMatch) {
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.shadowColor = healthColor;
      ctx.shadowBlur = 20;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  } else {
    // Normal node rendering (Radial Gradient)
    const grad = ctx.createRadialGradient(x, y - r * 0.3, r * 0.1, x, y, r);
    grad.addColorStop(0, lighten(color, hovered ? 40 : 25));
    grad.addColorStop(1, hovered ? lighten(color, 10) : color);
    
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();
    if (hovered || isSearchMatch) {
      ctx.shadowColor = node.color;
      ctx.shadowBlur = 20;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.stroke();
  }
  
  // Reset shadow for strokes
  ctx.shadowColor = 'transparent';
  
  // Inner subtle highlight (glass rim)
  ctx.beginPath();
  ctx.arc(x, y, Math.max(1, r - 1.5), 0, Math.PI * 2);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
  ctx.stroke();
  
  // Outer subtle border
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.lineWidth = 1;
  ctx.strokeStyle = darken(color, 15);
  ctx.stroke();

  // Bottom shading
  ctx.beginPath(); 
  ctx.arc(x, y + r * 0.3, r * 0.8, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0,0,0,0.08)'; 
  ctx.fill();
  
  ctx.restore();

  // Since it's a spread out horizontal tree, labels never overlap!
  const showLabel = true;
  
  if (showLabel) {
    const isDark = document.documentElement.classList.contains('dark');
    const fs = node.level === 0 ? 18 : node.level === 1 ? 14 : 11;
    ctx.font = `${node.level <= 1 ? '600 ' : '500 '}${fs}px Adani, Inter, system-ui`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    
    // Position label to the right of the node (Horizontal layout)
    const lx = x + r + 10;
    const label = node.name.length > 28 && !hovered ? node.name.slice(0, 26) + '..' : node.name;

    ctx.strokeStyle = isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 4;
    ctx.lineJoin = 'round';
    ctx.strokeText(label, lx, y);
    
    // Apply multi-color gradient to Project names based on mappings
    if (node.category === 3 || node.category === 4) {
      const hasP6 = !!node.p6;
      const hasSAP = node.sap && (node.sap.po_count > 0 || node.sap.inventory_items > 0 || node.sap.in_transit_count > 0);
      const hasTC = node.tc && (node.tc.lines?.length > 0 || node.tc.total_lines > 0);
      
      const activeColors = [];
      if (hasP6) activeColors.push('#3B82F6'); // Blue
      if (hasSAP) activeColors.push('#EC4899'); // Pink
      if (hasTC) activeColors.push('#EF4444'); // Red
      
      if (activeColors.length > 0) {
        const textWidth = ctx.measureText(label).width;
        const textGrad = ctx.createLinearGradient(lx, 0, lx + textWidth, 0);
        
        if (activeColors.length === 1) {
          textGrad.addColorStop(0, activeColors[0]);
          textGrad.addColorStop(1, activeColors[0]);
        } else if (activeColors.length === 2) {
          textGrad.addColorStop(0, activeColors[0]);
          textGrad.addColorStop(1, activeColors[1]);
        } else if (activeColors.length === 3) {
          textGrad.addColorStop(0, activeColors[0]);
          textGrad.addColorStop(0.5, activeColors[1]);
          textGrad.addColorStop(1, activeColors[2]);
        }
        
        ctx.fillStyle = textGrad;
      } else {
        ctx.fillStyle = isDark ? '#9CA3AF' : '#6B7280'; // Gray if no mappings
      }
    } else {
      ctx.fillStyle = isDark ? node.color : node.labelColor;
    }
    
    ctx.fillText(label, lx, y);

    if (node.mw_stats) {
      // 3-part colored rendering for Portfolio & EPS MW stats
      ctx.font = `11px Adani, Inter, system-ui`;
      ctx.strokeStyle = isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 3;
      
      const parts = [
        { text: `${node.mw_stats.total}`, color: '#3B82F6' },
        { text: `${node.mw_stats.cod}`, color: '#10B981' },
        { text: `${node.mw_stats.trial}`, color: '#F59E0B' }
      ];
      
      let currentLx = lx;
      parts.forEach((p, i) => {
        // Draw the number
        ctx.strokeText(p.text, currentLx, y + fs + 4);
        ctx.fillStyle = p.color;
        ctx.fillText(p.text, currentLx, y + fs + 4);
        currentLx += ctx.measureText(p.text).width;
        
        // Draw separator
        if (i < parts.length - 1) {
          const sep = ' / ';
          ctx.strokeText(sep, currentLx, y + fs + 4);
          ctx.fillStyle = isDark ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.3)';
          ctx.fillText(sep, currentLx, y + fs + 4);
          currentLx += ctx.measureText(sep).width;
        }
      });
      
    } else if (node.level === 1 && node.value) {
      ctx.font = `10px Adani, Inter, system-ui`;
      ctx.strokeStyle = isDark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255,255,255,0.85)';
      ctx.lineWidth = 3;
      const sub = node.value.split('·')[0]?.trim() || '';
      ctx.strokeText(sub, lx, y + fs + 4);
      ctx.fillStyle = isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)';
      ctx.fillText(sub, lx, y + fs + 4);
    }
  }

  ctx.globalAlpha = 1;
}

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
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-4 py-3 hover:bg-muted transition-colors">
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
        highlight === 'red' ? 'text-destructive' : highlight === 'green' ? 'text-success' : 'text-foreground'
      }`}>{value}</span>
    </div>
  );
}

function MiniCard({ label, value, sub }: { label: string; value: any; sub: string }) {
  return (
    <div className="bg-muted rounded-lg p-2 text-center border border-border">
      <div className="text-sm font-bold text-foreground">{value}</div>
      <div className="text-[8px] text-muted-foreground uppercase font-bold tracking-wider">{label}</div>
      <div className="text-[8px] text-muted-foreground">{sub}</div>
    </div>
  );
}
