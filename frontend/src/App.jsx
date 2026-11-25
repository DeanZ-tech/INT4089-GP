import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, Armchair, ArrowUpRight, BarChart3, Bell, CheckCircle2,
  ChevronRight, Clock3, Cpu, History, LayoutDashboard, LibraryBig, LockKeyhole,
  Pause, Play, Radio, RefreshCw, RotateCcw, ShieldCheck, UnlockKeyhole, Usb,
  Users, X, Zap, Layers3, Wrench, ChartNoAxesCombined,
} from 'lucide-react';

const API = '/api';
const LABELS = {IN_USE:'Occupied', AWAY:'Temporarily Away', FREE:'Available', LOCKED:'Awaiting Admin Release',UNKNOWN:'Checking',OFFLINE:'Offline'};
const REASONS = {WAIT_ADMIN:'管理员锁定：必须管理员确认', NORMAL:'传感器证据一致',STABILIZING:'正在稳定确认', SENSOR_CONFLICT:'椅垫与测距存在冲突', DISTANCE_INVALID:'测距无效',TRAY_UNKNOWN:'托盘状态未知'};
const SCENARIO_NAMES = {NORMAL:'Normal Day',PEAK:'Peak Hours', LOW:'Low Occupancy', ALERTS:'Absence Alerts'};
const FNUM = n => String(n ?? 0).padStart(2,'0');
const pct = n => `${Number(n || 0).toFixed(1)}%`;
const formatDuration = ms => `${FNUM(Math.floor((ms || 0)/60000))}:${FNUM(Math.floor(((ms || 0)/1000)%60))}`;
const dateLabel = t => t ? new Date(t).toLocaleString('zh-CN', {hour12:false}) : '—';
const countBadge = n => n > 0 ? <span className="nav-count">{n}</span> : null;

function EventText({event}) {
  const d = event.detail || {};
  if (event.kind === 'state_change') return `Real A01 · ${d.from || 'UNKNOWN'} → ${d.to || 'UNKNOWN'}`;
  if (event.kind === 'sim_state_change') return `Simulated ${d.id} · ${d.from} → ${d.to}`;
  if (event.kind === 'sim_admin_release') return `Simulated ${d.id} · administrator release`;
  if (event.kind === 'boot') return `Arduino startup · ${d.locked ? 'lock restored' : 'monitoring ready'}`;
  if (event.kind === 'release_requested') return 'Real A01 · administrator release requested';
  if (event.kind === 'admin_ack') return `Arduino acknowledged · ${d.result}`;
  if (event.kind === 'device_error') return `Device error · ${d.code}`;
  if (event.kind === 'simulation_control') return `Simulator · ${d.scenario} / ${d.speed}×`;
  return event.kind;
}

function Metric({label,value,hint,icon:Icon,accent}) {
  return <div className="stat-card"><div className="stat-head">{label}<Icon size={19}/></div>
    <div className={`stat-big ${accent || ''}`}>{value}</div><div className="stat-foot">{hint}</div></div>;
}

function FloorCard({floor, selected, onClick}) {
  return <button className={`floor-card ${selected ? 'floor-card-active':''}`} onClick={onClick}>
    <div className="floor-card-title"><span><Layers3 size={17}/><b>{floor.name}</b></span><span className={`crowd-pill ${floor.crowd_level.toLowerCase()}`}>{floor.crowd_level}</span></div>
    <small>{floor.area} · seat occupancy proxy</small>
    <div className="floor-card-numbers"><strong>{floor.physically_occupied}<span> / {floor.capacity}</span></strong><span>{pct(floor.occupancy_pct)}</span></div>
    <div className="floor-progress"><div style={{width:`${floor.occupancy_pct}%`}} className={`level-${floor.crowd_level.toLowerCase()}`}/></div>
    <div className="floor-card-foot">{floor.available} available · {floor.locked} locked</div>
  </button>;
}

function SeatTile({seat,selected,onClick}) {
  return <button onClick={onClick} title={`${seat.id} · ${seat.source} · ${seat.state}`} className={`seat-mini seat-${seat.state.toLowerCase()} ${selected?'seat-selected':''}`}>
    <Armchair size={21} strokeWidth={2.3}/><b>{seat.id}</b>
    <small>{seat.source === 'ARDUINO' ? 'REAL' : seat.source === 'DEMO_INPUT' ? 'DEMO INPUT' : 'SIM'}</small>
    {seat.locked && <LockKeyhole className="mini-lock" size={13}/>}
  </button>;
}

function OccupancyLine({points, field='physically_occupied', max=20}) {
  if (!points?.length) return <div className="chart-empty">Collecting live snapshots... Chart data is recorded every 10 seconds.</div>;
  const width=900,height=245,padL=45,padT=18,padB=30,padR=10;
  const bounds = Math.max(1, max);
  const x = i => padL+(i/Math.max(1,points.length-1))*(width-padL-padR);
  const y = v => padT+(1-Math.min(1,Math.max(0,v)/bounds))*(height-padT-padB);
  const path = points.map((p,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(p[field] || 0).toFixed(2)}`).join(' ');
  const area = `${path} L${x(points.length-1)},${height-padB} L${x(0)},${height-padB} Z`;
  const last=points[points.length-1];
  return <div className="line-chart-wrap"><svg className="line-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Recorded seat occupancy over time">
    <defs><linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#179c88" stopOpacity=".28"/><stop offset="1" stopColor="#179c88" stopOpacity="0"/></linearGradient></defs>
    {[0,.25,.5,.75,1].map(f=><g key={f}><line x1={padL} y1={y(bounds*f)} x2={width-padR} y2={y(bounds*f)} stroke="#e6eef4" strokeDasharray="3 5"/><text x={padL-9} y={y(bounds*f)+4} textAnchor="end" fontSize="12" fill="#8294a7">{Math.round(bounds*f)}</text></g>)}
    <path d={area} fill="url(#chartGradient)"/><path d={path} fill="none" stroke="#008b79" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"/>
    <circle cx={x(points.length-1)} cy={y(last[field]||0)} r="5" fill="#008b79" stroke="white" strokeWidth="2"/>
    <text x={padL} y={height-7} fill="#8294a7" fontSize="12">{new Date(points[0].time).toLocaleTimeString('zh-CN',{hour12:false})}</text>
    <text x={width-padR} y={height-7} textAnchor="end" fill="#8294a7" fontSize="12">{new Date(last.time).toLocaleTimeString('zh-CN',{hour12:false})}</text>
  </svg></div>;
}

export default function App() {
  const [status,setStatus] = useState(null);
  const [world,setWorld] = useState(null);
  const [events,setEvents] = useState([]);
  const [section,setSection] = useState('overview');
  const [floor,setFloor] = useState('F1');
  const [selectedId,setSelectedId] = useState('F1-01');
  const [connectedWS,setConnectedWS] = useState(false);
  const [showRelease,setShowRelease] = useState(false);
  const [token,setToken] = useState('');
  const [releasing,setReleasing] = useState(false);
  const [notice,setNotice] = useState('');
  const [showRaw,setShowRaw] = useState(false);
  const [trend,setTrend] = useState(null);
  const [analysisFloor,setAnalysisFloor] = useState('ALL');

  const load = async () => {
    try {
      const [s,e,w] = await Promise.all([fetch(`${API}/status`),fetch(`${API}/events`),fetch(`${API}/world`)]);
      if(s.ok)setStatus(await s.json()); if(e.ok)setEvents(await e.json()); if(w.ok)setWorld(await w.json());
    } catch { setConnectedWS(false); }
  };
  useEffect(()=>{
    let active=true,socket,retry;
    const open=()=>{
      if(!active)return;
      socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);
      socket.onopen=()=>{if(active)setConnectedWS(true)};
      socket.onmessage=ev=>{if(!active)return;try {const msg=JSON.parse(ev.data);
        if(msg.kind==='update'){setStatus(msg.status);fetch(`${API}/events`).then(r=>r.ok?r.json():[]).then(setEvents).catch(()=>{});}
        if(msg.kind==='world'){setWorld(msg.world);}
      }catch{/* ignore */}};
      socket.onclose=()=>{if(active){setConnectedWS(false);retry=setTimeout(open,2500)}};
    };
    load();open();const timer=setInterval(load,8000);
    return()=>{active=false;clearInterval(timer);clearTimeout(retry);socket?.close()};
  },[]);
  useEffect(()=>{
    if(section!=='analytics')return;
    let active=true;
    const get=()=>fetch(`${API}/analytics/occupancy?floor_id=${analysisFloor}&limit=100`)
      .then(r=>r.ok?r.json():null).then(d=>{if(active)setTrend(d)}).catch(()=>{});
    get();const timer=setInterval(get,10000);
    return()=>{active=false;clearInterval(timer)};
  },[section,analysisFloor]);
  const selected=world?.seats?.find(s=>s.id===selectedId);
  const floors=world?.floors || [];
  const summary=world?.summary || {};
  const realSummary=world?.real_summary || {};
  const simulation=world?.simulation || {scenario:'NORMAL',speed:1,running:true};
  const realStatus=status?.reading;
  const isRealSelected=selected?.source === 'ARDUINO' || selected?.source === 'DEMO_INPUT';
  const activeLock=!!status?.locked;
  const deviceOnline=!!status?.connected;
  const activeLockCount=summary.locked||0;
  const mapSeats=world?.seats?.filter(s=>s.floor_id===floor) || [];
  const title=section==='overview'?'Smart Library Overview':section==='seats'?'Seat Management':section==='alerts'?'Alert Center':section==='analytics'?'Data Analysis':section==='resources'?'Resource Optimization':'Event History';
  const eventRows=useMemo(()=>section==='overview'?events.slice(0,5):events,[events,section]);

  async function sendRelease() {
    if(!selected)return;
    setReleasing(true);setNotice('');
    try{
      const url=isRealSelected?`${API}/seats/A01/release`:`${API}/simulated-seats/${selected.id}/release`;
      const r=await fetch(url,{method:'POST',headers:{'X-Admin-Token':token}});
      const d=await r.json();if(!r.ok)throw Error(d.detail || 'Release failed');
      setNotice(isRealSelected?'Release command sent; waiting for Arduino ACK.':'Simulated seat lock released by administrator.');
      setShowRelease(false);setToken('');await load();
    }catch(err){setNotice(`Release failed: ${err.message}`)}finally{setReleasing(false)}
  }
  async function controlSim(changes){
    try{
      const r=await fetch(`${API}/simulation/control`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(changes)});
      if(!r.ok)throw Error((await r.json()).detail || 'Simulation control failed');
      const w=await fetch(`${API}/world`);if(w.ok)setWorld(await w.json());
    }catch(err){setNotice(`Simulation control: ${err.message}`)}
  }
  function viewSeat(s){setSelectedId(s.id);setFloor(s.floor_id)}
  function NavItem({id,icon:Icon,label,count,small}){return <button type="button" className={`nav-item ${section===id?'selected':''}`} onClick={()=>setSection(id)}><Icon size={18}/><span>{label}</span>{small&&<em className="nav-coming">SOON</em>}{countBadge(count)}</button>}
  const AlertRows = () => <div className="alert-grid">{world?.seats?.filter(s=>s.locked).map(s=><div className="alert-content" key={s.id}>
    <AlertTriangle size={22} className="alert-icon"/><div className="alert-summary"><b>{s.id} · Awaiting Admin Release</b><p>{s.source==='SIMULATED'?'Simulated timeout event':'Arduino hardware timeout lock'} · Sensor state: {LABELS[s.physical]||s.physical}</p></div>
    <button className="release-btn" disabled={!s.online || (s.id==='F1-01'&&status?.pending_release)} onClick={()=>{viewSeat(s);setShowRelease(true)}}><UnlockKeyhole size={15}/> Review & Release</button>
  </div>)}{!activeLockCount&&<div className="empty-alert"><CheckCircle2 size={22}/> No active timeout locks</div>}</div>;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><LibraryBig size={22}/></div><div><strong>smartlibrary</strong><small>MANAGEMENT CONSOLE</small></div></div>
      <div className="nav-label">WORKSPACE</div>
      <nav><NavItem id="overview" icon={LayoutDashboard} label="Dashboard"/><NavItem id="seats" icon={Armchair} label="Seat Management"/>
        <NavItem id="alerts" icon={Bell} label="Alerts" count={activeLockCount}/><NavItem id="analytics" icon={ChartNoAxesCombined} label="Data Analysis"/>
        <NavItem id="history" icon={History} label="Event History"/><NavItem id="resources" icon={Wrench} label="Resource Optimization" small/></nav>
      <div className="side-bottom"><div className="side-device"><Cpu size={18}/><div><b>Arduino UNO</b><small>Real hardware · F1-01 / A01</small></div></div>
        <span className={`side-status ${deviceOnline?'connected':''}`}><span className="status-dot"/>{deviceOnline?'USB connected':'Device offline · no fabricated data'}</span>
        <div className="version">SMART LIBRARY · v2.0 · 1 REAL + 59 SIM</div></div>
    </aside>
    <div className="main-panel"><header className="topbar"><div className="breadcrumb">Smart Library <ChevronRight size={14}/><b>{title}</b></div>
      <div className="top-actions"><span className="protocol"><Usb size={15}/> Arduino JSONL V1</span><span className="admin-pill"><ShieldCheck size={15}/> Admin Portal</span></div></header>
    <main className="page">
      <div className="page-title"><div><div className="eyebrow">MULTI-FLOOR / LIVE + SIMULATED SEATS</div><h1>{title}</h1>
        <p>One real Arduino sensor kit, 59 stateful simulation seats. All analytics are computed from current and recorded seat states.</p></div>
        <div className="title-badges"><span className={`live-pill ${deviceOnline?'on':''}`}><Radio size={15}/>{deviceOnline?'Arduino Connected':'Arduino Offline'}</span><button className="refresh-btn" onClick={load}><RefreshCw size={16}/></button></div></div>
      <div className="source-notice"><span><span className="source-dot real"/>1 Real Arduino Seat (F1-01 / A01)</span><span><span className="source-dot sim"/>59 Simulated Seats</span><span>Floor crowd = seat occupancy proxy · No footfall sensor</span></div>
      {status?.mode==='DEMO'&&<div className="demo-banner"><Zap size={17}/> Input demonstration mode is enabled: A01 is simulated as well.</div>}
      {notice&&<div className="notice"><span>{notice}</span><button onClick={()=>setNotice('')}><X size={16}/></button></div>}
      {status?.backend_error&&<div className="error-banner"><AlertTriangle size={18}/>{status.backend_error}</div>}

      {(section==='overview'||section==='seats')&&<>
        <section className="stat-grid">
          <Metric label="LIBRARY SEATS" value={FNUM(summary.capacity)} hint="3 floors · 1 real + 59 simulated" icon={Armchair}/>
          <Metric label="PHYSICALLY OCCUPIED" value={FNUM(summary.physically_occupied)} hint={`Seat occupancy: ${pct(summary.occupancy_pct)}`} icon={Users}/>
          <Metric label="AVAILABLE SEATS" value={FNUM(summary.available)} hint="Confirmed free · unlocked · online" icon={CheckCircle2}/>
          <Metric label="AWAITING REVIEW" value={FNUM(summary.locked)} hint="Timeout locks requiring admin release" icon={Bell} accent={summary.locked?'warning-text':''}/>
        </section>
        <section className="panel floor-section"><div className="panel-heading"><div><h2>Floor Occupancy & Crowd Level</h2><p>Real-time seat-based crowd indicator · not measured footfall</p></div><span className="pale-tag">LIVE AGGREGATES</span></div>
          <div className="floor-grid">{floors.map(f=><FloorCard floor={f} key={f.id} selected={floor===f.id} onClick={()=>{setFloor(f.id);setSelectedId(`${f.id}-01`)}}/>)}</div>
        </section>
        <section className="content-grid new-map-grid">
          <div className="panel"><div className="panel-heading"><div><h2>Seat Availability Overview</h2><p>{floor} · 20 seats · select any seat for details</p></div><span className="pale-tag">{floor==='F1'?'1 REAL + 19 SIM':'20 SIMULATED'}</span></div>
            <div className="floor-tabs">{floors.map(f=><button key={f.id} className={floor===f.id?'active':''} onClick={()=>{setFloor(f.id);setSelectedId(`${f.id}-01`)}}>{f.name}</button>)}</div>
            <div className="seat-map">{mapSeats.map(s=><SeatTile seat={s} key={s.id} selected={s.id===selectedId} onClick={()=>viewSeat(s)}/>)}</div>
            <div className="seat-legend"><span><i className="seat-swatch in_use"/> Occupied</span><span><i className="seat-swatch free"/> Free</span><span><i className="seat-swatch away"/> Away</span><span><i className="seat-swatch locked"/> Locked</span><span><i className="seat-swatch offline"/> Offline / Unknown</span></div>
          </div>
          <div className="panel selected-panel"><div className="panel-heading"><div><h2>{selected?.id || 'Seat'} · Live Details</h2><p>{isRealSelected?'Physical Arduino UNO telemetry':'Stateful simulated seat'}</p></div><span className={`source-tag ${isRealSelected?'tag-real':'tag-sim'}`}>{isRealSelected?'REAL':'SIMULATED'}</span></div>
            {selected&&<><div className="selected-feature"><div className={`selected-icon seat-${selected.state.toLowerCase()}`}><Armchair size={28}/></div><div><div className="muted">EFFECTIVE SEAT STATUS</div><h3>{LABELS[selected.state] || selected.state}</h3><small>{selected.online?'Reporting':'Offline · not available'}</small></div></div>
              {selected.locked&&<div className="lock-warning"><LockKeyhole size={20}/><div><b>Administrator release required</b><p>Returning visitors do not override the timeout lock.</p></div></div>}
              <div className="details-row"><span>Physical occupancy</span><b>{LABELS[selected.physical] || selected.physical}</b></div>
              <div className="details-row"><span>Away timer</span><b className="mono">{formatDuration(selected.away_ms)}</b></div>
              <div className="details-row"><span>Assignable</span><b>{selected.available?'Yes':'No'}</b></div>
              <div className="details-row"><span>Source</span><b>{selected.source}</b></div>
              {isRealSelected&&<><div className="details-row"><span>Decision reason</span><b>{REASONS[realStatus?.reason] || realStatus?.reason || 'No data'}</b></div>
                <button className="raw-toggle" onClick={()=>setShowRaw(!showRaw)}>{showRaw?'Hide':'View'} raw Arduino JSON <ArrowUpRight size={16}/></button>
                {showRaw&&<pre className="raw-data">{JSON.stringify(realStatus,null,2)||'Waiting for Arduino...'}</pre>}</>}
              {selected.locked&&<button className="release-btn wide-release" disabled={!selected.online||(isRealSelected&&status?.pending_release)} onClick={()=>setShowRelease(true)}><UnlockKeyhole size={16}/> {isRealSelected&&status?.pending_release?'Waiting for Arduino ACK':'Review & Release'}</button>}
            </>}
          </div>
        </section>
        {section==='overview'&&<div className="panel sensor-panel"><div className="panel-heading"><div><h2>Real Sensor Monitoring · A01</h2><p>These values are from Arduino, never generated by the seat simulator</p></div><span className="pale-tag">{deviceOnline?'USB LIVE':'NO LIVE DATA'}</span></div>
          <div className="sensor-grid"><div className="sensor-card"><div className="sensor-icon"><Armchair size={23}/></div><div className="sensor-name">Seat Pressure <span>D2</span></div><strong>{deviceOnline&&realStatus?(realStatus.seat?'PRESSED':'CLEAR'):'NO DATA'}</strong><small>Physical switch</small></div>
            <div className="sensor-card"><div className="sensor-icon"><Activity size={23}/></div><div className="sensor-name">Desk Tray <span>A0</span></div><strong>{deviceOnline&&realStatus?(realStatus.tray===null?'UNKNOWN':realStatus.tray?'PRESSED':'CLEAR'):'NO DATA'}</strong><small>Raw analog: {deviceOnline&&realStatus?realStatus.tray_raw:'—'}</small></div>
            <div className="sensor-card"><div className="sensor-icon"><Radio size={23}/></div><div className="sensor-name">Distance <span>I2C</span></div><strong>{deviceOnline&&realStatus?(realStatus.distance_valid?`${realStatus.distance_mm} mm`:'INVALID'):'NO DATA'}</strong><small>VL53L0X ToF</small></div></div>
        </div>}
        {section==='overview'&&<div className="panel sim-controls"><div className="panel-heading"><div><h2>Simulation Control</h2><p>Controls 59 simulated seats only. Real A01 is never overwritten.</p></div><span className="pale-tag">DEMO TOOLS</span></div>
          <div className="sim-control-row"><label>Scenario<select value={simulation.scenario} onChange={e=>controlSim({scenario:e.target.value})}>{Object.entries(SCENARIO_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
            <label>Speed<select value={simulation.speed} onChange={e=>controlSim({speed:Number(e.target.value)})}>{[1,5,10].map(n=><option key={n} value={n}>{n}×</option>)}</select></label>
            <button className="sim-action" onClick={()=>controlSim({running:!simulation.running})}>{simulation.running?<Pause size={16}/>:<Play size={16}/>} {simulation.running?'Pause':'Resume'}</button>
            <button className="sim-action secondary" onClick={()=>controlSim({reset:true})}><RotateCcw size={16}/> Reset simulation</button></div>
          <p className="sim-footnote">Reset affects simulated seats only. Existing Arduino locks and serial commands are unchanged.</p>
        </div>}
      </>}

      {section==='analytics'&&<>
        <div className="analytics-banner"><BarChart3 size={22}/><div><strong>Recorded Seat Analytics · Not Footfall</strong><p>All figures are calculated from current seat states and SQLite snapshots. The physical A01 sensor updates Floor 1 and library totals in real time.</p></div></div>
        <div className="analytics-filters"><label>Trend source <select value={analysisFloor} onChange={e=>setAnalysisFloor(e.target.value)}><option value="ALL">All 60 Seats · Mixed Sources</option><option value="REAL">Real Arduino A01 Only</option>{floors.map(f=><option value={f.id} key={f.id}>{f.name} · Includes simulations</option>)}</select></label><span>Snapshot interval: ~10s</span></div>
        <section className="stat-grid">
          <Metric label="SEAT OCCUPANCY" value={pct(analysisFloor==='REAL'?realSummary.occupancy_pct:analysisFloor==='ALL'?summary.occupancy_pct:floors.find(f=>f.id===analysisFloor)?.occupancy_pct)} hint="Physically occupied / seat capacity" icon={Users}/>
          <Metric label="PHYSICALLY OCCUPIED" value={FNUM(analysisFloor==='REAL'?realSummary.physically_occupied:analysisFloor==='ALL'?summary.physically_occupied:floors.find(f=>f.id===analysisFloor)?.physically_occupied)} hint="Based on current sensor / simulator states" icon={Activity}/>
          <Metric label="AVAILABLE SEATS" value={FNUM(analysisFloor==='REAL'?realSummary.available:analysisFloor==='ALL'?summary.available:floors.find(f=>f.id===analysisFloor)?.available)} hint="Confirmed free and unlocked" icon={CheckCircle2}/>
          <Metric label="LOCKED SEATS" value={FNUM(analysisFloor==='REAL'?realSummary.locked:analysisFloor==='ALL'?summary.locked:floors.find(f=>f.id===analysisFloor)?.locked)} hint="Awaiting administrator" icon={Bell}/>
        </section>
        <div className="panel analytics-chart"><div className="panel-heading"><div><h2>Recorded Occupancy Trend</h2><p>Physical seat occupancy over time · sourced from SQLite observations</p></div><span className="pale-tag">DYNAMIC HISTORY</span></div>
          <OccupancyLine points={trend?.points} max={analysisFloor==='REAL'?1:analysisFloor==='ALL'?60:20}/>
          <div className="chart-caption">{trend?.points?.length||0} recorded observations · New samples appear automatically; no static example series.</div>
        </div>
        <div className="panel analytics-chart"><div className="panel-heading"><div><h2>Live Floor Comparison</h2><p>Each bar is calculated from the same shared seat state as Dashboard</p></div><span className="pale-tag">LIVE</span></div>
          <div className="floor-compare">{floors.map(f=><div className="compare-row" key={f.id}><div><b>{f.name}</b><small>{f.physically_occupied} occupied of {f.capacity} seats</small></div><div className="compare-track"><div style={{width:`${f.occupancy_pct}%`}} className={`level-${f.crowd_level.toLowerCase()}`}/></div><strong>{pct(f.occupancy_pct)}</strong></div>)}</div>
        </div>
        <div className="source-notice">Real A01 may show offline, and simulation data is not evidence of actual visitors. No measured footfall, entry counts, or energy savings are claimed.</div>
      </>}

      {section==='resources'&&<div className="panel soon-panel"><div className="soon-icon"><Wrench size={35}/></div><span className="coming-tag">PHASE C · COMING SOON</span><h2>Resource Optimization</h2><p>Energy-saving and staff-allocation recommendations are planned for a future phase. No automatic lighting, HVAC, or workforce controls are implemented.</p><div className="soon-features"><span><Zap size={17}/> Lighting Recommendations</span><span><Users size={17}/> Staff Allocation</span><span><ChartNoAxesCombined size={17}/> Energy Analysis</span></div></div>}

      {section==='alerts'&&<div className="panel"><div className="panel-heading"><div><h2>Timeout Alerts</h2><p>All locked seats require administrator release. Real and simulated sources stay separate.</p></div><span className="pale-tag">{summary.locked||0} ACTIVE LOCKS</span></div><AlertRows/></div>}
      {section==='overview'&&summary.locked>0&&<div className="panel alert-panel"><div className="panel-heading"><div><h2>Admin Review</h2><p>Timeout locks persist until administrator release</p></div><button className="small-link" onClick={()=>setSection('alerts')}>View all <ChevronRight size={16}/></button></div><div className="alert-summary"><b>{summary.locked} seat(s) awaiting release</b></div></div>}
      {(section==='history'||section==='overview')&&<div className="panel history-panel"><div className="panel-heading"><div><h2>Recent Events</h2><p>Backend event records · SIMULATED events are labeled</p></div><button className="small-link" onClick={()=>setSection(section==='overview'?'history':'overview')}>{section==='overview'?'View all':'Back to overview'} <ChevronRight size={16}/></button></div>
        {eventRows.length?<div className="event-list">{eventRows.map(e=><div className="event-line" key={e.id}><div className={`event-dot ${e.kind.startsWith('sim_')?'yellow':'blue'}`}/><div><strong><EventText event={e}/></strong><small>{e.kind.startsWith('sim_')||e.kind==='simulation_control'?'SIMULATED':'ARDUINO / BACKEND'} · {e.kind}</small></div><time>{dateLabel(e.time)}</time></div>)}</div>:<div className="history-empty"><Clock3 size={24}/> No events yet</div>}</div>}
      <footer className="footer"><span>Smart Library V2 · 1 Real Seat + 59 Simulated · Arduino UNO × FastAPI × React</span><span>{connectedWS?'WebSocket connected':'WebSocket reconnecting...'}</span></footer>
    </main></div>
    {showRelease&&selected&&<div className="modal-scrim" role="presentation" onMouseDown={()=>setShowRelease(false)}><div className="modal" role="dialog" aria-modal="true" aria-label={`Release ${selected.id}`} onMouseDown={e=>e.stopPropagation()}><button className="modal-close" onClick={()=>setShowRelease(false)}><X size={19}/></button><div className="modal-icon"><LockKeyhole size={25}/></div><h2>Release seat {selected.id}?</h2><p>{isRealSelected?'A01 is controlled by the physical Arduino. The seat remains sensor-driven after the hardware ACK.':'This is a simulated seat. Admin approval clears only this simulated timeout lock.'}</p><label htmlFor="admin-token">Administrator token</label><input id="admin-token" type="password" autoComplete="off" placeholder="Token configured in Python" value={token} onChange={e=>setToken(e.target.value)}/><div className="modal-actions"><button className="cancel-btn" onClick={()=>setShowRelease(false)}>Cancel</button><button className="release-btn" disabled={!token||releasing} onClick={sendRelease}>{releasing?'Sending…':'Confirm release'}</button></div></div></div>}
  </div>;
}
