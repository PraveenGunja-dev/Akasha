"use client";

import { cn } from "../../lib/utils";
import React, { useState, useEffect, createContext, useContext } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { IconMenu2, IconX } from "@tabler/icons-react";

/* The collapsed rail is the ONLY width the sidebar occupies in layout.
   Expanding floats the panel over the page instead of widening it, so hovering
   the sidebar never reflows the dashboard behind it. */
export const RAIL_W = 76;
export const PANEL_W = 268;

/* One easing curve and one duration for every sidebar motion. */
const EASE = [0.4, 0, 0.2, 1] as const;
const DURATION = 0.28;
export const SIDEBAR_TRANSITION = { duration: DURATION, ease: EASE };

interface SidebarContextProps {
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  animate: boolean;
  /** true when the panel is showing labels — collapsed rail otherwise */
  expanded: boolean;
}

const SidebarContext = createContext<SidebarContextProps | undefined>(undefined);

export const useSidebar = () => {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
};

/** Desktop and mobile render mutually exclusively — never both at once, so the
    active-pill layout animation only ever has one element to fly between. */
function useIsDesktop() {
  const query = "(min-width: 768px)";
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window === "undefined" ? true : window.matchMedia(query).matches
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    setIsDesktop(mq.matches);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return isDesktop;
}

export const SidebarProvider = ({
  children,
  open: openProp,
  setOpen: setOpenProp,
  animate = true,
}: {
  children: React.ReactNode;
  open?: boolean;
  setOpen?: React.Dispatch<React.SetStateAction<boolean>>;
  animate?: boolean;
}) => {
  const [openState, setOpenState] = useState(false);

  const open = openProp !== undefined ? openProp : openState;
  const setOpen = setOpenProp !== undefined ? setOpenProp : setOpenState;

  return (
    <SidebarContext.Provider
      value={{ open, setOpen, animate, expanded: animate ? open : true }}
    >
      {children}
    </SidebarContext.Provider>
  );
};

export const Sidebar = ({
  children,
  open,
  setOpen,
  animate,
}: {
  children: React.ReactNode;
  open?: boolean;
  setOpen?: React.Dispatch<React.SetStateAction<boolean>>;
  animate?: boolean;
}) => {
  return (
    <SidebarProvider open={open} setOpen={setOpen} animate={animate}>
      {children}
    </SidebarProvider>
  );
};

export const SidebarBody = (props: React.ComponentProps<typeof motion.div>) => {
  const isDesktop = useIsDesktop();
  return isDesktop ? (
    <DesktopSidebar {...props} />
  ) : (
    <MobileSidebar {...(props as unknown as React.ComponentProps<"div">)} />
  );
};

export const DesktopSidebar = ({
  className,
  children,
  ...props
}: React.ComponentProps<typeof motion.div>) => {
  const { setOpen, animate, expanded } = useSidebar();

  return (
    /* Fixed-width spacer: what the page layout actually reserves. */
    <div
      className="relative h-full shrink-0"
      style={{ width: animate ? RAIL_W : PANEL_W }}
    >
      {/* Floating panel: grows over the content, never pushes it. */}
      <motion.div
        initial={false}
        animate={{ width: expanded ? PANEL_W : RAIL_W }}
        transition={SIDEBAR_TRANSITION}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className={cn(
          "absolute inset-y-0 left-0 z-50 flex flex-col overflow-hidden rounded-r-2xl",
          "transition-shadow duration-300 ease-in-out",
          expanded
            ? "shadow-[0_24px_70px_-16px_rgba(11,116,177,0.35)]"
            : "shadow-none",
          className
        )}
        {...props}
      >
        {children}
      </motion.div>
    </div>
  );
};

export const MobileSidebar = ({
  className,
  children,
  ...props
}: React.ComponentProps<"div">) => {
  const { open, setOpen } = useSidebar();
  return (
    <div
      className={cn(
        "relative z-50 flex h-14 w-full flex-row items-center justify-between px-4",
        className
      )}
      {...props}
    >
      <div className="z-20 flex w-full justify-end">
        <IconMenu2
          className="cursor-pointer text-foreground"
          onClick={() => setOpen(!open)}
        />
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ x: "-100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "-100%", opacity: 0 }}
            transition={SIDEBAR_TRANSITION}
            className={cn(
              "fixed inset-0 z-[100] flex h-full w-full flex-col justify-between p-10",
              className
            )}
          >
            <div
              className="absolute right-6 top-6 z-50 cursor-pointer text-foreground"
              onClick={() => setOpen(!open)}
            >
              <IconX />
            </div>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

/* px-4 here + px-2.5 on the list container centres a 24px icon box exactly on
   the 76px rail's midline, so icons don't drift as the panel opens. */
export const SidebarLink = ({
  link,
  className,
  active = false,
  ...props
}: {
  link: {
    label: string;
    href: string;
    icon: React.JSX.Element | React.ReactNode;
  };
  className?: string;
  active?: boolean;
} & React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
  const { expanded } = useSidebar();

  return (
    <a
      href={link.href}
      className={cn(
        "group/sidebar relative flex items-center gap-2.5 rounded-lg px-4 py-[7px]",
        "transition-colors duration-200 ease-in-out",
        active
          ? "text-white"
          : "text-muted-foreground hover:bg-brand-blue/10 hover:text-foreground",
        className
      )}
      {...props}
    >
      {/* The selection pill slides between items instead of blinking on/off. */}
      {active && (
        <motion.span
          layoutId="sidebar-active-pill"
          transition={SIDEBAR_TRANSITION}
          className="absolute inset-0 rounded-lg bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink shadow-md shadow-brand-purple/30"
        />
      )}
      <span className="relative z-10 flex h-5 w-6 shrink-0 items-center justify-center">
        {link.icon}
      </span>
      <motion.span
        initial={false}
        animate={{ opacity: expanded ? 1 : 0, x: expanded ? 0 : -6 }}
        transition={SIDEBAR_TRANSITION}
        style={{ pointerEvents: expanded ? "auto" : "none" }}
        className="relative z-10 whitespace-nowrap text-[13px] font-medium leading-tight"
      >
        {link.label}
      </motion.span>
    </a>
  );
};
