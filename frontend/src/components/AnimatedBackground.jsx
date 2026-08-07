export default function AnimatedBackground() {
  const motionEnabled = localStorage.getItem('edusense_ambient_motion') !== 'false'
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-mesh opacity-60 dark:opacity-40" />
      <div className={`${motionEnabled ? 'animate-blob' : ''} absolute -left-32 top-0 h-[28rem] w-[28rem] rounded-full bg-gradient-to-br from-mint/35 to-teal-400/10 blur-3xl`} />
      <div className={`${motionEnabled ? 'animate-blob animation-delay-2000' : ''} absolute -right-24 top-1/4 h-[30rem] w-[30rem] rounded-full bg-gradient-to-bl from-ocean/30 to-indigo-500/10 blur-3xl`} />
      <div className={`${motionEnabled ? 'animate-blob animation-delay-4000' : ''} absolute bottom-0 left-1/3 h-96 w-96 rounded-full bg-gradient-to-tr from-coral/20 to-amber-400/5 blur-3xl`} />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(71,196,166,0.10),transparent_42%)] dark:bg-[radial-gradient(circle_at_top,rgba(71,196,166,0.14),transparent_38%)]" />
      <div className={`${motionEnabled ? 'hero-glow' : ''} absolute left-1/2 top-0 h-64 w-64 -translate-x-1/2 rounded-full bg-mint/10 blur-3xl`} />
    </div>
  )
}
