/* Functional motion only: a short stagger so a dense screen resolves in a
   readable order instead of snapping in all at once. 160ms, ease-out, 8px of
   travel — matching --dur-base / --ease in index.css. No decorative loops. */
export const containerVariants: any = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.035 } },
};

export const itemVariants: any = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.16, ease: [0.2, 0, 0, 1] } },
};
