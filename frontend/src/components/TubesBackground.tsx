import { useEffect, useRef } from 'react'

/** Lightweight animated tube field for the login backdrop; no external WebGL/CDN dependency. */
export function TubesBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d', { alpha: true })
    if (!canvas || !context) return

    const ctx = context
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointer = { x: 0.5, y: 0.45, tx: 0.5, ty: 0.45 }
    let width = 0
    let height = 0
    let pixelRatio = 1
    let frame = 0
    let frameCount = 0

    const resize = () => {
      width = window.innerWidth
      height = window.innerHeight
      pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5)
      canvas.width = Math.round(width * pixelRatio)
      canvas.height = Math.round(height * pixelRatio)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    }

    const trackPointer = (event: PointerEvent) => {
      pointer.tx = event.clientX / Math.max(width, 1)
      pointer.ty = event.clientY / Math.max(height, 1)
    }

    const draw = (now: number) => {
      frame = window.requestAnimationFrame(draw)
      frameCount += 1
      if (document.hidden || frameCount % 2 === 0) return

      pointer.x += (pointer.tx - pointer.x) * 0.035
      pointer.y += (pointer.ty - pointer.y) * 0.035
      ctx.clearRect(0, 0, width, height)

      const time = reduceMotion.matches ? 0 : now * 0.00018
      const centerY = height * (0.46 + (pointer.y - 0.5) * 0.08)
      const cursorBend = (pointer.x - 0.5) * width * 0.11
      const strands = width < 700 ? 5 : 8
      const points = width < 700 ? 48 : 76

      for (let strand = 0; strand < strands; strand += 1) {
        const depth = strand / Math.max(strands - 1, 1)
        const phase = strand * 0.82 + time * (strand % 2 ? 0.8 : -0.65)
        const amplitude = height * (0.11 + depth * 0.12)
        const path: Array<[number, number]> = []
        for (let point = 0; point <= points; point += 1) {
          const progress = point / points
          const x = progress * width
          const wave = Math.sin(progress * Math.PI * 2.2 + phase) * amplitude
            + Math.sin(progress * Math.PI * 4.1 - phase * 0.7) * amplitude * 0.17
          const bend = Math.sin(progress * Math.PI) * cursorBend * (depth - 0.45)
          const y = centerY + wave + bend + (depth - 0.5) * height * 0.18
          path.push([x, y])
        }

        const opacity = 0.12 + (1 - depth) * 0.19
        const lineWidth = 1.4 + depth * 2.4
        const gradient = ctx.createLinearGradient(0, centerY - amplitude, width, centerY + amplitude)
        gradient.addColorStop(0, `rgba(162, 9, 3, ${opacity})`)
        gradient.addColorStop(0.48, `rgba(179, 85, 55, ${opacity * 0.8})`)
        gradient.addColorStop(1, `rgba(208, 196, 192, ${opacity * 0.42})`)

        const strokePath = (offsetY = 0) => {
          ctx.beginPath()
          path.forEach(([x, y], index) => index === 0 ? ctx.moveTo(x, y + offsetY) : ctx.lineTo(x, y + offsetY))
          ctx.stroke()
        }

        ctx.save()
        ctx.lineCap = 'round'
        ctx.lineJoin = 'round'
        ctx.strokeStyle = gradient
        ctx.lineWidth = lineWidth * 3.6
        ctx.shadowColor = strand % 3 === 0 ? 'rgba(162, 9, 3, .32)' : 'rgba(179, 85, 55, .24)'
        ctx.shadowBlur = 22
        strokePath()
        ctx.shadowBlur = 0
        ctx.lineWidth = lineWidth
        strokePath()
        ctx.strokeStyle = `rgba(208, 196, 192, ${opacity * 0.58})`
        ctx.lineWidth = Math.max(0.7, lineWidth * 0.2)
        strokePath(-lineWidth * 0.42)
        ctx.restore()
      }
    }

    resize()
    window.addEventListener('resize', resize, { passive: true })
    window.addEventListener('pointermove', trackPointer, { passive: true })
    frame = window.requestAnimationFrame(draw)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', trackPointer)
    }
  }, [])

  return <canvas ref={canvasRef} className="login-tubes-canvas" aria-hidden="true" />
}
