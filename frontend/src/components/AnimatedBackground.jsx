export default function AnimatedBackground() {
  const motionEnabled = localStorage.getItem('edusense_ambient_motion') !== 'false'
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Animated gradient blobs */}
      <div className={`${motionEnabled ? 'animate-blob' : ''} absolute -left-32 top-0 h-96 w-96 rounded-full bg-mint/30 blur-3xl`} />
      <div className={`${motionEnabled ? 'animate-blob animation-delay-2000' : ''} absolute -right-24 top-1/3 h-[26rem] w-[26rem] rounded-full bg-ocean/25 blur-3xl`} />
      <div className={`${motionEnabled ? 'animate-blob animation-delay-4000' : ''} absolute bottom-0 left-1/4 h-80 w-80 rounded-full bg-coral/20 blur-3xl`} />
      
      {/* Subtle gradient overlays */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(71,196,166,0.08),transparent_45%)] dark:bg-[radial-gradient(circle_at_top,rgba(71,196,166,0.12),transparent_40%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.04),transparent)] opacity-60" />
    </div>
  )
}
