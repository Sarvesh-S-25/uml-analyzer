import { useEffect, useRef } from 'react'

/** Decorative background inspired by the approved minimal reference.
 * It never receives pointer events and writes only CSS variables, so moving the
 * mouse cannot trigger React renders or interfere with application controls. */
export function AmbientBackdrop() {
  const backdrop = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = backdrop.current
    if (!element || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let frame = 0
    let targetX = 0
    let targetY = 0
    let currentX = 0
    let currentY = 0

    const move = (event: PointerEvent) => {
      targetX = (event.clientX / window.innerWidth - 0.5) * 32
      targetY = (event.clientY / window.innerHeight - 0.5) * 24
    }

    const animate = () => {
      currentX += (targetX - currentX) * 0.075
      currentY += (targetY - currentY) * 0.075
      element.style.setProperty('--aqua-x', `${(-currentX * 0.72).toFixed(2)}px`)
      element.style.setProperty('--aqua-y', `${(-currentY * 0.72).toFixed(2)}px`)
      element.style.setProperty('--rose-x', `${(currentX * 0.58).toFixed(2)}px`)
      element.style.setProperty('--rose-y', `${(currentY * 0.58).toFixed(2)}px`)
      element.style.setProperty('--grid-x', `${(currentX * 0.18).toFixed(2)}px`)
      element.style.setProperty('--grid-y', `${(currentY * 0.18).toFixed(2)}px`)
      frame = window.requestAnimationFrame(animate)
    }

    window.addEventListener('pointermove', move, { passive: true })
    frame = window.requestAnimationFrame(animate)
    return () => {
      window.removeEventListener('pointermove', move)
      window.cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div ref={backdrop} className="ambient-backdrop" aria-hidden="true">
      <div className="ambient-grid" />
      <div className="ambient-orbit ambient-orbit-aqua" />
      <div className="ambient-orbit ambient-orbit-rose" />
      <div className="ambient-blob ambient-blob-aqua" />
      <div className="ambient-blob ambient-blob-rose" />
    </div>
  )
}
