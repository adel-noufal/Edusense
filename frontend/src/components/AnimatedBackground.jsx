export default function AnimatedBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden transform-gpu">
      <div className="absolute inset-0 bg-mesh opacity-40 dark:opacity-20" />
      <div className="absolute -left-20 -top-20 h-96 w-96 rounded-full bg-teal-400/10 dark:bg-teal-500/5 pointer-events-none" />
      <div className="absolute -right-20 top-1/4 h-[30rem] w-[30rem] rounded-full bg-sky-500/10 dark:bg-sky-500/5 pointer-events-none" />
      <div className="absolute bottom-0 left-1/3 h-80 w-80 rounded-full bg-indigo-500/10 dark:bg-indigo-500/5 pointer-events-none" />
    </div>
  )
}
