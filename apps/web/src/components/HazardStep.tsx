import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { Brief, Flood } from '../api'
import { LEGEND } from '../api'
import { DepthChip, metres } from './common'

const GSI_PALE = 'https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'
const FLOOD_TILES = 'https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin_data/{z}/{x}/{y}.png'

export function HazardMap({ brief, highlight, height = 460 }: { brief: Brief; highlight?: string | null; height?: number }) {
  const { home, shelters } = brief
  const chosen = highlight ?? brief.suggested_shelter_id
  const route = brief.route_to_suggested
  return (
    <div className="map" style={{ height }}>
      <MapContainer center={[home.lat, home.lon]} zoom={14} style={{ height: '100%' }} scrollWheelZoom={false}>
        <TileLayer url={GSI_PALE} attribution='<a href="https://maps.gsi.go.jp/development/ichiran.html">地理院タイル</a>' maxZoom={18} />
        <TileLayer url={FLOOD_TILES} opacity={0.6} maxNativeZoom={17} maxZoom={18}
          attribution='<a href="https://disaportal.gsi.go.jp/">ハザードマップポータルサイト</a>' />
        {route && chosen === brief.suggested_shelter_id && (
          <Polyline positions={route.path} pathOptions={{ color: '#1d2b36', weight: 3, dashArray: '6 6' }} />
        )}
        {shelters.map((s) => (
          <CircleMarker key={s.id} center={[s.lat, s.lon]} radius={s.id === chosen ? 10 : 7}
            pathOptions={{ color: '#fff', weight: 2, fillOpacity: 1, fillColor: s.certified_for_flood ? '#2b4e8c' : '#74838f' }}>
            <Tooltip direction="top">{s.id} {s.name}{s.certified_for_flood ? '' : ' (not designated for floods)'}</Tooltip>
          </CircleMarker>
        ))}
        <CircleMarker center={[home.lat, home.lon]} radius={9} pathOptions={{ color: '#fff', weight: 3, fillColor: '#c4382c', fillOpacity: 1 }}>
          <Tooltip permanent direction="right">Home (district point)</Tooltip>
        </CircleMarker>
      </MapContainer>
    </div>
  )
}

function Gauge({ flood }: { flood: Flood }) {
  const bands = [...LEGEND].reverse()
  return (
    <div className="gauge" role="img" aria-label={`Home flood depth: ${flood.label_en}`}>
      {bands.map((b) => {
        const here = flood.status === 'in_zone' && flood.class_id === b.id
        return [
          <div key={`${b.id}-band`} className="gauge-band" style={{ background: b.color }} />,
          <div key={`${b.id}-label`} className={`gauge-label${here ? ' here' : ''}`}>
            <span>{b.en}</span>{here && <em>home</em>}
          </div>,
        ]
      })}
    </div>
  )
}

export function HazardStep({ brief, onNext }: { brief: Brief; onNext: () => void }) {
  const { home, shelters, route_to_suggested: route } = brief
  return (
    <div className="hazard">
      <div>
        <HazardMap brief={brief} />
        <div className="map-legend small muted">
          {LEGEND.map((l) => <span key={l.id} className="depth" style={{ ['--swatch' as string]: l.color }}>{l.en}</span>)}
          <span><span style={{ color: '#2b4e8c' }}>●</span> shelter designated for floods</span>
          <span><span style={{ color: '#74838f' }}>●</span> not designated for floods</span>
        </div>
      </div>
      <div className="panel panel-pad">
        <h2 className="section-title">Before the visit</h2>
        <p className="small muted">Maximum-scale flood scenario (想定最大規模), read from the national hazard map at the home point.</p>
        <Gauge flood={home.flood} />
        {home.flood.status !== 'in_zone' && (
          <p className="small" style={{ marginBottom: 12 }}>
            No mapped flood zone here. That is not proof of safety: prefectural-river coverage is partial.
          </p>
        )}
        <h3 className="section-title" style={{ fontSize: 14 }}>Nearest flood shelters</h3>
        <ul className="shelters">
          {shelters.map((s) => (
            <li key={s.id} className={s.id === brief.suggested_shelter_id ? 'suggested' : ''}>
              <span className="sid">{s.id}</span>
              <span>
                <b>{s.name}</b>
                <span className="small muted" style={{ display: 'block' }}>
                  {s.certified_for_flood ? 'Designated for floods' : 'Not designated for floods'}
                  {s.id === brief.suggested_shelter_id && ', suggested'}
                </span>
                <DepthChip flood={s.flood_at_site} />
              </span>
              <span className="small">{metres(s.distance_m)}</span>
            </li>
          ))}
        </ul>
        {route && (
          <p className="small" style={{ marginTop: 10 }}>
            Route to {brief.suggested_shelter_id}: {metres(route.distance_m)}
            {route.duration_s ? `, about ${Math.round(route.duration_s / 60)} min on foot` : ''}.{' '}
            Deepest mapped water on the way: {route.worst_flood_on_path.label_en}.
            {route.method === 'straight_line' && <span className="muted"> Straight-line distance; walking route not computed.</span>}
          </p>
        )}
        <div className="actions" style={{ marginTop: 16 }}>
          <button className="btn primary" onClick={onNext}>Start the conversation</button>
        </div>
        <p className="attrib">
          Sources: {brief.attributions.map((a, i) => (
            <span key={a.url}>{i > 0 && '; '}<a href={a.url} target="_blank" rel="noreferrer">{a.label}</a></span>
          ))}
        </p>
      </div>
    </div>
  )
}
