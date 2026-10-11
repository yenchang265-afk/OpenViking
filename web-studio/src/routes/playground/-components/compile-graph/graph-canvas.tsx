import { useEffect, useRef } from 'react'
import { drag } from 'd3-drag'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
} from 'd3-force'
import type { SimulationLinkDatum, SimulationNodeDatum } from 'd3-force'
import { select } from 'd3-selection'
import type { Selection } from 'd3-selection'
import { zoom, zoomIdentity } from 'd3-zoom'
import type { ZoomBehavior } from 'd3-zoom'

import {
  PHYSICS,
  groupColor,
  nodeRadius,
  shortLabel,
} from '../../-lib/compile-graph/style'
import type {
  CompiledGraph,
  GraphLink,
  GraphNode,
} from '../../-lib/compile-graph/types'

type SimNode = GraphNode & SimulationNodeDatum
type SimLink = Omit<GraphLink, 'source' | 'target'> &
  SimulationLinkDatum<SimNode> & { curve: number }

const endpoint = (end: string | number | SimNode) =>
  typeof end === 'object' ? end : null
const endpointId = (end: string | number | SimNode) =>
  typeof end === 'object' ? end.id : String(end)

/** Parallel edges between one pair bend apart so their labels stay legible. */
function withCurves(links: readonly GraphLink[]): SimLink[] {
  const pairs = new Map<string, number>()
  const pairKey = (l: GraphLink) => [l.source, l.target].sort().join('\u0000')
  for (const link of links)
    pairs.set(pairKey(link), (pairs.get(pairKey(link)) ?? 0) + 1)
  const seen = new Map<string, number>()
  return links.map((link) => {
    const key = pairKey(link)
    const index = seen.get(key) ?? 0
    seen.set(key, index + 1)
    return { ...link, curve: (index - ((pairs.get(key) ?? 1) - 1) / 2) * 0.23 }
  })
}

/** Path from the source edge to just outside the target, curved by `curve`. */
function linkPath(link: SimLink, kind: CompiledGraph['kind']) {
  const s = endpoint(link.source)
  const t = endpoint(link.target)
  if (!s || !t) return ''
  const [sx, sy, tx, ty] = [s.x ?? 0, s.y ?? 0, t.x ?? 0, t.y ?? 0]
  const dx = tx - sx
  const dy = ty - sy
  const length = Math.hypot(dx, dy) || 1
  const cx = (sx + tx) / 2 - (dy / length) * length * link.curve
  const cy = (sy + ty) / 2 + (dx / length) * length * link.curve
  // Stop at the target's rim so the arrow head stays visible.
  const back = kind === 'knowledge-graph' ? nodeRadius(kind, t.degree) + 3 : 0
  const ux = tx - cx
  const uy = ty - cy
  const ul = Math.hypot(ux, uy) || 1
  const ex = tx - (ux / ul) * back
  const ey = ty - (uy / ul) * back
  return link.curve
    ? `M${sx},${sy}Q${cx},${cy} ${ex},${ey}`
    : `M${sx},${sy}L${ex},${ey}`
}

function labelPoint(link: SimLink): [number, number] {
  const s = endpoint(link.source)
  const t = endpoint(link.target)
  if (!s || !t) return [0, 0]
  const [sx, sy, tx, ty] = [s.x ?? 0, s.y ?? 0, t.x ?? 0, t.y ?? 0]
  const length = Math.hypot(tx - sx, ty - sy) || 1
  const cx = (sx + tx) / 2 - ((ty - sy) / length) * length * link.curve
  const cy = (sy + ty) / 2 + ((tx - sx) / length) * length * link.curve
  return [
    0.25 * sx + 0.5 * cx + 0.25 * tx,
    0.25 * sy + 0.5 * cy + 0.25 * ty - 5,
  ]
}

type Built = {
  nodes: Selection<SVGGElement, SimNode, SVGGElement, unknown>
  links: Selection<SVGPathElement, SimLink, SVGGElement, unknown>
  labels: Selection<SVGTextElement, SimLink, SVGGElement, unknown>
  zoom: ZoomBehavior<SVGSVGElement, unknown>
}

export type GraphCanvasProps = {
  graph: CompiledGraph
  /** Ids drawn at full strength; `null` shows everything. */
  highlighted: ReadonlySet<string> | null
  selectedId: string | null
  onSelect: (id: string) => void
  /** Changing this value recenters the view. */
  resetSignal: number
  label: string
}

export function GraphCanvas({
  graph,
  highlighted,
  selectedId,
  onSelect,
  resetSignal,
  label,
}: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const builtRef = useRef<Built | null>(null)
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    const element = svgRef.current
    if (!element) return
    const { kind } = graph
    const physics = PHYSICS[kind]
    const svg = select(element)
    svg.selectAll('*').remove()
    const box = () => element.getBoundingClientRect()
    const nodes: SimNode[] = graph.nodes.map((node) => ({ ...node }))
    const links = withCurves(graph.links)

    const root = svg.append('g')
    const zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.25, 4])
      .on('zoom', (event) => root.attr('transform', event.transform.toString()))
    svg.call(zoomBehavior).on('dblclick.zoom', null)

    if (kind === 'knowledge-graph')
      svg
        .append('defs')
        .append('marker')
        .attr('id', 'compile-graph-arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 9)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-4L9,0L0,4')
        .attr('class', 'fill-muted-foreground')

    const linkSel = root
      .append('g')
      .attr('fill', 'none')
      .selectAll<SVGPathElement, SimLink>('path')
      .data(links)
      .join('path')
      .attr('class', 'stroke-muted-foreground')
      .attr('stroke-width', 1.1)
      .attr(
        'marker-end',
        kind === 'knowledge-graph' ? 'url(#compile-graph-arrow)' : null,
      )
    linkSel
      .append('title')
      .text((d) => (d.relation ? `${d.label} · ${d.relation}` : d.label))

    const labelSel = root
      .append('g')
      .selectAll<SVGTextElement, SimLink>('text')
      .data(kind === 'knowledge-graph' ? links : [])
      .join('text')
      .attr('class', 'fill-muted-foreground text-[10px]')
      .attr('text-anchor', 'middle')
      .attr('opacity', 0)
      .text((d) => d.label)

    const nodeSel = root
      .append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('tabindex', 0)
      .attr('role', 'button')
      .attr('aria-label', (d) => d.title)
      .attr(
        'class',
        'cursor-pointer focus-visible:outline-2 focus-visible:outline-ring',
      )
      .on('click', (_event, d) => onSelectRef.current(d.id))
      .on('keydown', (event: KeyboardEvent, d) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        onSelectRef.current(d.id)
      })
    nodeSel
      .append('circle')
      .attr('r', (d) => nodeRadius(kind, d.degree))
      .attr('fill', (d) => groupColor(kind, d.group))
      .attr('class', 'stroke-background')
      .attr('stroke-width', 2)
    nodeSel
      .append('text')
      .attr('x', (d) => nodeRadius(kind, d.degree) + 5)
      .attr('dy', '0.35em')
      .attr('class', 'fill-foreground text-[11px] select-none')
      .text((d) => shortLabel(d.title))
    nodeSel.append('title').text((d) => d.title)

    const { width, height } = box()
    const simulation = forceSimulation(nodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(physics.distance)
          .strength(physics.strength),
      )
      .force('charge', forceManyBody().strength(physics.charge))
      .force('center', forceCenter(width / 2, height / 2))
      .force(
        'collide',
        forceCollide<SimNode>()
          .radius((d) => nodeRadius(kind, d.degree) + physics.collide)
          .iterations(2),
      )
      .on('tick', () => {
        linkSel.attr('d', (d) => linkPath(d, kind))
        labelSel.each(function (d) {
          const [x, y] = labelPoint(d)
          select(this).attr('x', x).attr('y', y)
        })
        nodeSel.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
      })

    nodeSel.call(
      drag<SVGGElement, SimNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        }),
    )

    const observer = new ResizeObserver(() => {
      const next = box()
      simulation.force('center', forceCenter(next.width / 2, next.height / 2))
      simulation.alpha(0.3).restart()
    })
    observer.observe(element)
    builtRef.current = {
      nodes: nodeSel,
      links: linkSel,
      labels: labelSel,
      zoom: zoomBehavior,
    }
    return () => {
      observer.disconnect()
      simulation.stop()
      builtRef.current = null
    }
  }, [graph])

  useEffect(() => {
    const built = builtRef.current
    if (!built) return
    const lit = (id: string) => !highlighted || highlighted.has(id)
    const touchesSelected = (d: SimLink) =>
      endpointId(d.source) === selectedId || endpointId(d.target) === selectedId
    built.nodes.attr('opacity', (d) => (lit(d.id) ? 1 : 0.1))
    built.nodes
      .select('circle')
      .attr('class', (d) =>
        d.id === selectedId ? 'stroke-foreground' : 'stroke-background',
      )
      .attr('stroke-width', (d) => (d.id === selectedId ? 3 : 2))
    built.links.attr('opacity', (d) =>
      !highlighted
        ? 0.55
        : lit(endpointId(d.source)) && lit(endpointId(d.target))
          ? 0.9
          : 0.05,
    )
    built.labels.attr('opacity', (d) => (touchesSelected(d) ? 1 : 0))
  }, [graph, highlighted, selectedId])

  useEffect(() => {
    const element = svgRef.current
    const built = builtRef.current
    if (!element || !built || resetSignal === 0) return
    select(element).call(built.zoom.transform, zoomIdentity)
  }, [resetSignal])

  return (
    <svg
      ref={svgRef}
      role="group"
      aria-label={label}
      className="size-full touch-none bg-background"
    />
  )
}
