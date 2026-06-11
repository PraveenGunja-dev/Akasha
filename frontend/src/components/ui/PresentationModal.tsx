import React, { useState, useEffect } from 'react';
import { X, ChevronLeft, ChevronRight, Maximize2, Minimize2 } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

interface PresentationModalProps {
  isOpen: boolean;
  onClose: () => void;
  totalSlides?: number;
}

export default function PresentationModal({ isOpen, onClose, totalSlides = 10 }: PresentationModalProps) {
  const [currentSlide, setCurrentSlide] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
        if (e.key === 'ArrowRight' || e.key === 'Space') handleNext();
        if (e.key === 'ArrowLeft') handlePrev();
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = 'unset';
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, currentSlide]);

  const handleNext = () => {
    if (currentSlide < totalSlides) setCurrentSlide(prev => prev + 1);
  };

  const handlePrev = () => {
    if (currentSlide > 1) setCurrentSlide(prev => prev - 1);
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 backdrop-blur-sm"
      >
        <div className={`relative flex flex-col w-full mx-auto transition-all duration-300 ${isFullscreen ? 'h-full max-w-full' : 'h-[85vh] max-w-6xl rounded-2xl overflow-hidden shadow-2xl border border-white/10'}`}>
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 bg-[#0B1020] border-b border-white/10 shrink-0">
            <div className="flex items-center gap-3">
              <div className="px-3 py-1 bg-primary/20 text-primary text-xs font-semibold rounded-full border border-primary/30">
                Slide {currentSlide} of {totalSlides}
              </div>
              <h3 className="text-white font-medium text-sm hidden sm:block">AGEL AKASHA Cross Functional Intelligence</h3>
            </div>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
              </button>
              <button 
                onClick={onClose}
                className="p-2 text-red-400 hover:text-red-300 hover:bg-red-400/10 rounded-lg transition-colors"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {/* Slide Viewer */}
          <div className="relative flex-1 bg-[#050810] flex items-center justify-center group overflow-hidden">
            <motion.img 
              key={currentSlide}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3 }}
              src={`/slides/slide_${currentSlide}.png`} 
              alt={`Slide ${currentSlide}`} 
              className="max-w-full max-h-full object-contain shadow-[0_0_50px_rgba(0,0,0,0.5)]"
            />

            {/* Navigation Arrows */}
            <button 
              onClick={(e) => { e.stopPropagation(); handlePrev(); }}
              disabled={currentSlide === 1}
              className={`absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white backdrop-blur-md border border-white/10 transition-all ${currentSlide === 1 ? 'opacity-0 pointer-events-none' : 'opacity-0 group-hover:opacity-100 hover:bg-primary/50 hover:scale-110'}`}
            >
              <ChevronLeft size={32} />
            </button>

            <button 
              onClick={(e) => { e.stopPropagation(); handleNext(); }}
              disabled={currentSlide === totalSlides}
              className={`absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white backdrop-blur-md border border-white/10 transition-all ${currentSlide === totalSlides ? 'opacity-0 pointer-events-none' : 'opacity-0 group-hover:opacity-100 hover:bg-primary/50 hover:scale-110'}`}
            >
              <ChevronRight size={32} />
            </button>
          </div>

          {/* Progress Bar */}
          <div className="h-1 bg-gray-800 shrink-0">
            <div 
              className="h-full bg-gradient-to-r from-primary to-purple-500 transition-all duration-300 ease-out"
              style={{ width: `${(currentSlide / totalSlides) * 100}%` }}
            />
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
