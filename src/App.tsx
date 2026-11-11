import { useEffect, useMemo, useRef, useState } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from 'ag-grid-community';
import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, BadgeCheck, BarChart3, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Code2, Download, ExternalLink, FileText, FlaskConical, History, Layers3, Leaf, Link2, LoaderCircle, LockKeyhole, Menu, Play, Plus, ScanLine, Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Terminal, TriangleAlert, Wallet, X } from 'lucide-react';
import type { Audit, Evidence, Health, Mandate, Offer, Scenario,PayPalCheckout } from './types';
import ProductDiscovery from './ProductDiscovery';
import {Search} from 'lucide-react';

ModuleRegistry.registerModules([AllCommunityModule]);
const gridTheme=themeQuartz.withParams({backgroundColor:'#10151c',foregroundColor:'#c3ccd8',headerBackgroundColor:'#141a22',headerTextColor:'#8b98aa',borderColor:'#232c38',rowHoverColor:'#18232b',fontFamily:'Inter, ui-sans-serif, system-ui',fontSize:12,headerFontSize:10,rowBorder:{color:'#1e2732'},wrapperBorder:false,cellHorizontalPadding:16});
const money=(n:number|string|null|undefined,currency='USD')=>{
  if(n==null)return '—';
  if(currency==='UNKNOWN')return Number(n).toFixed(2)+' (currency unknown)';
  try{return new Intl.NumberFormat('en-US',{style:'currency',currency}).format(Number(n))}catch{return Number(n).toFixed(2)+' '+currency}
};
const num=(n:number|null|undefined,d=2)=>n==null?'—':n.toFixed(d);
const defaultMandate:Mandate={product_url:'http://127.0.0.1:8765/store/clean',scenario:'clean',market_mode:'synthetic',market_query:'',max_spend:100,purchase_carbon_cap:8,monthly_carbon_cap:50,max_fees:5,no_subscription:true,detect_anchor:true,offset_opt_in:false,override_policy:'strict',override_acknowledged:false,override_reason:'',destination:'New York, US',cart:[]};
const scenarios=[{id:'clean' as const,name:'Clean purchase',sub:'Transparent pricing',icon:BadgeCheck},{id:'anchor' as const,name:'Anchor + drip pricing',sub:'Fees & recurring terms',icon:TriangleAlert},{id:'carbon' as const,name:'Carbon cap violation',sub:'Gross emissions > cap',icon:Leaf}];
function isDemoProduct(url:string){try{const parsed=new URL(url);return [new URL(defaultMandate.product_url).origin,'http://127.0.0.1:8000'].includes(parsed.origin)&&/^\/store\/(clean|anchor|carbon)$/.test(parsed.pathname)}catch{return false}}
type Tab='overview'|'evidence'|'methodology';
async function api<T>(path:string,body?:unknown):Promise<T>{
  const r=await fetch(path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){const data=await r.json().catch(()=>null);throw new Error(typeof data?.detail==='string'?data.detail:JSON.stringify(data?.detail??'Request failed'));}
  return r.json();
}
function Badge({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){return <span className={`badge ${tone}`}>{children}</span>}
function SectionTitle({icon:Icon,title,aside}:{icon:typeof Activity;title:string;aside?:React.ReactNode}){return <div className="section-title"><h2><Icon size={15}/>{title}</h2>{aside}</div>}

export default function App(){
  const [mandate,setMandate]=useState<Mandate>(defaultMandate);
  const [audit,setAudit]=useState<Audit|null>(null);
  const [health,setHealth]=useState<Health|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[tab,setTab]=useState<Tab>('overview');
  const [dirty,setDirty]=useState(false),[approved,setApproved]=useState(false),[paymentBusy,setPaymentBusy]=useState(false);
  const [receipt,setReceipt]=useState<Record<string,unknown>|null>(null),[order,setOrder]=useState<PayPalCheckout|null>(null);
  const [drawer,setDrawer]=useState<'history'|'connections'|null>(null),[history,setHistory]=useState<{id:string;name:string;decision:string;created_at:string}[]>([]);
  const [cartText,setCartText]=useState(''),[cartOpen,setCartOpen]=useState(false),[filter,setFilter]=useState('all');
  const [mobileNav,setMobileNav]=useState(false),[elapsed,setElapsed]=useState(0);
  const [selectedOffer,setSelectedOffer]=useState<Offer|null>(null);
  const [view,setView]=useState<'terminal'|'discovery'>('terminal');
  const [discoveryUrl,setDiscoveryUrl]=useState('');
  const loaded=useRef(false);
  async function loadHealth(){try{setHealth(await api<Health>('/api/health'))}catch{setError('API is offline. Start FastAPI with npm run api, then run an audit.')}}
  async function restoreCheckout(auditId?:string,orderId?:string){
    const query=new URLSearchParams();if(auditId)query.set('audit_id',auditId);if(orderId)query.set('order_id',orderId);
    const existing=await api<PayPalCheckout|null>('/api/paypal/checkout?'+query);
    if(!existing)return false;
    const original=await api<Audit>('/api/audits/'+encodeURIComponent(existing.audit_id));
    setAudit(original);setMandate({...defaultMandate,...original.mandate});setOrder(existing);setDirty(false);setApproved(false);setReceipt(null);
    localStorage.setItem('qct-checkout',JSON.stringify({audit_id:existing.audit_id,order_id:existing.order_id}));
    if(existing.capture_completed)setReceipt({mode:'PAYPAL_SANDBOX',status:'COMPLETED',order_id:existing.order_id});
    return true;
  }
  useEffect(()=>{if(loaded.current)return;loaded.current=true;loadHealth();
    async function initialize(){
      const params=new URLSearchParams(location.search),id=params.get('audit')??undefined;
      const orderId=params.get('order')??params.get('token')??undefined;
      try{
        if(params.get('discover')){openDiscovery(params.get('discover')!);return}
        if(params.has('new')){await runAudit(defaultMandate);return}
        if(id||orderId||params.has('paypal')){
          const restored=await restoreCheckout(id,orderId);
          if(!restored&&id&&!params.has('paypal')){const a=await api<Audit>('/api/audits/'+encodeURIComponent(id));setAudit(a);setMandate({...defaultMandate,...a.mandate})}
          else if(!restored)setError('This PayPal return could not be linked to a saved checkout. No new purchase was started. Open audit history to recover it.');
          if(params.get('paypal')==='cancelled')setError('PayPal checkout was cancelled or returned without approval. No capture was requested.');
          return;
        }
        let saved:{audit_id?:string;order_id?:string}|null=null;
        try{saved=JSON.parse(localStorage.getItem('qct-checkout')??'null')}catch{}
        if(saved&&(await restoreCheckout(saved.audit_id,saved.order_id)))return;
        if(await restoreCheckout())return;
        await runAudit(defaultMandate);
      }catch(e){setError((e as Error).message)}
    }
    initialize();
  },[]);
  useEffect(()=>{if(!busy)return;setElapsed(0);const id=setInterval(()=>setElapsed(n=>n+1),1000);return()=>clearInterval(id)},[busy]);
  function update<K extends keyof Mandate>(key:K,value:Mandate[K]){setMandate(m=>({...m,[key]:value}));setDirty(true);setApproved(false);setReceipt(null);setOrder(null)}
  async function runAudit(input:Mandate=mandate){
    setSelectedOffer(null);
    setBusy(true);setError('');setApproved(false);setReceipt(null);setOrder(null);
    try{const next={...input};if(cartText.trim()&&input===mandate){const parsed=JSON.parse(cartText);if(!Array.isArray(parsed))throw new Error('Cart must be a JSON array.');next.cart=parsed;}
      const result=await api<Audit>('/api/audits',next);setAudit(result);setMandate(next);setDirty(false);loadHealth();
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  function openDiscovery(url=''){setDiscoveryUrl(url);setView('discovery')}
  function submitProduct(){if(isDemoProduct(mandate.product_url))runAudit();else openDiscovery(mandate.product_url)}
  function deepAudit(url:string){const next={...mandate,product_url:url,market_mode:'live' as const,cart:[]};setView('terminal');setMandate(next);setCartText('');runAudit(next)}
  function selectScenario(id:Scenario){setView('terminal');const next={...defaultMandate,scenario:id,product_url:new URL(`/store/${id}`,defaultMandate.product_url).toString()};setMandate(next);setCartText('');setTab('overview');setDirty(true);runAudit(next)}
  async function switchOffer(offer:Offer){if(!isDemoProduct(offer.url)){openDiscovery(offer.url);return}const next={...mandate,product_url:offer.url,cart:[]};setMandate(next);setCartText('');setDirty(true);await runAudit(next)}
  async function settle(mode:'sandbox'|'simulate'|'capture'){
    if(!audit)return;setPaymentBusy(true);setError('');
    try{const result=await api<Record<string,unknown>>(mode==='sandbox'?'/api/paypal/orders':mode==='capture'?'/api/paypal/capture':'/api/payments/simulate',{audit_id:audit.id,buyer_approved:approved,approved_total:audit.fiat.total,...(mode==='capture'?{order_id:order?.order_id}:{})});
      if(mode==='sandbox'){
        const created=result as unknown as {order_id:string;approval_url:string;status:string;amount:string};
        setOrder({audit_id:audit.id,...created,currency:'USD',mode:'PAYPAL_SANDBOX',paypal_status:created.status,approval_verified:false,capture_completed:false,audit_expired:false,warning:null});
        localStorage.setItem('qct-checkout',JSON.stringify({audit_id:audit.id,order_id:created.order_id}));
        window.location.assign(created.approval_url);
      }
      else{setReceipt(result);setApproved(false);if(mode==='capture')localStorage.removeItem('qct-checkout');loadHealth()}
    }catch(e){setError((e as Error).message)}finally{setPaymentBusy(false)}
  }
  async function refreshCheckout(){if(!order)return;setPaymentBusy(true);setError('');try{await restoreCheckout(order.audit_id,order.order_id)}catch(e){setError((e as Error).message)}finally{setPaymentBusy(false)}}
  function payOrResume(){
    if(order&&!order.approval_verified){if(order.approval_url)window.location.assign(order.approval_url);return}
    settle(order?'capture':'sandbox');
  }
  function download(){if(!audit)return;const url=URL.createObjectURL(new Blob([JSON.stringify(audit,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`qct-audit-${audit.id}.json`;a.click();URL.revokeObjectURL(url)}
  async function showHistory(){setDrawer('history');try{setHistory(await api('/api/audits'))}catch(e){setError((e as Error).message)}}
  const offers=useMemo(()=>(audit?.offers??[]).filter(o=>filter==='all'||o.match===filter),[audit,filter]);
  const offerColumns=useMemo<ColDef<Offer>[]>(()=>[
    {headerName:'MERCHANT / PRODUCT',field:'merchant',flex:2,minWidth:235,tooltipValueGetter:p=>p.data?.name,cellRenderer:({data}:ICellRendererParams<Offer>)=><span className="merchant-cell"><span className="merchant-avatar">{data?.merchant[0]}</span><span className="merchant-product"><strong>{data?.merchant}</strong><small>{data?.name}</small></span></span>},
    {headerName:'MATCH',field:'match',minWidth:128,flex:1,cellRenderer:({value}:ICellRendererParams)=><span className={`match ${value==='identical'?'green':'muted'}`}>{value==='identical'?<Check size={12}/>:<Layers3 size={12}/>} {value}</span>},
    {headerName:'ITEM PRICE',field:'price',minWidth:120,flex:.8,valueFormatter:p=>p.data?`${Number(p.value).toFixed(2)} ${p.data.currency}`:'—',cellClass:'mono price-cell'},
    {headerName:'VS. CURRENT',minWidth:125,flex:.9,valueGetter:p=>audit&&p.data&&audit.product.advertised!=null&&audit.market.currency!=='UNKNOWN'&&p.data.currency===audit.market.currency?Number(p.data.price)-Number(audit.product.advertised):null,cellRenderer:({value}:ICellRendererParams)=><span className={`mono ${value!=null&&value<0?'green':'muted'}`}>{value==null?'Not comparable':`${value<0?'−':'+'}${money(Math.abs(value),audit?.market.currency)}`}</span>},
    {headerName:'SOURCE',minWidth:90,flex:.7,cellRenderer:({data}:ICellRendererParams<Offer>)=><span className={`source-label ${data?.synthetic?'':'green'}`}>{data?.synthetic?'MOCK':'LIVE'}</span>},
    {headerName:'',minWidth:146,flex:1,sortable:false,cellRenderer:({data}:ICellRendererParams<Offer>)=>data&&<div className="offer-actions"><a href={data.url} target="_blank" rel="noreferrer" title="Open merchant"><ExternalLink size={13}/></a><button onClick={()=>switchOffer(data)} disabled={busy}>Re-audit <ArrowUpRight size={12}/></button></div>}
  ],[audit,busy]);
  const evidenceColumns=useMemo<ColDef<Evidence>[]>(()=>[
    {field:'id',headerName:'REF',width:80,cellClass:'mono green'},
    {field:'field',headerName:'FIELD',width:175},
    {field:'value',headerName:'OBSERVED VALUE',flex:1,minWidth:250,tooltipField:'value'},
    {field:'selector',headerName:'DOM SELECTOR',width:230,cellClass:'mono'},
    {headerName:'SOURCE',width:130,valueGetter:p=>p.data?.synthetic?'SYNTHETIC':'EXTERNAL DOM'},
  ],[]);
  const pass=audit?.decision==='PASS'&&!dirty&&!busy;
  const checkoutBlocked=Boolean(order&&(order.audit_expired||order.warning));
  const sandboxEligible=Boolean(audit?.product.controlled&&!new URL(audit.product.url).searchParams.has('offer'));
  const violations=audit?.findings.filter(f=>f.severity!=='INFO')??[];
  const gross=audit?.carbon.gross_kg;
  const monthlyUsed=health?.ledger.carbon??audit?.carbon.monthly_used??0;

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav?'mobile-open':''}`}>
      <a href="/" className="brand"><div className="brand-icon"><Terminal size={21}/></div><span>QCT<span className="brand-dot">.</span><small>COMMERCE INTELLIGENCE</small></span></a>
      <div className="workspace-switch"><span className="workspace-avatar">Q</span><div>Hackathon workspace<small>Personal terminal</small></div><ChevronDown size={13}/></div>
      <span className="nav-label">WORKSPACE</span>
      <nav>
        <button className={!drawer&&tab==='overview'?'active':''} onClick={()=>{setTab('overview');setDrawer(null);setMobileNav(false)}}><Activity size={17}/> Commerce terminal <span className="nav-live"/></button>
        <button className={tab==='evidence'?'active':''} onClick={()=>{setTab('evidence');setDrawer(null);setMobileNav(false)}}><ScanLine size={17}/> Evidence explorer <span className="nav-count">{audit?.evidence.length??0}</span></button>
        <button onClick={showHistory}><History size={17}/> Audit history</button>
        <button className={tab==='methodology'?'active':''} onClick={()=>{setTab('methodology');setDrawer(null)}}><BookOpen size={17}/> Methodology</button>
      </nav>
      <span className="nav-label second-label">INFRASTRUCTURE</span>
      <nav><button onClick={()=>setDrawer('connections')}><Link2 size={17}/> Connections <span className="nav-count">3</span></button><button onClick={()=>document.getElementById('mandate-panel')?.scrollIntoView({behavior:'smooth'})}><SlidersHorizontal size={17}/> Buyer mandates</button></nav>
      <div className="sidebar-bottom"><div className="sandbox-card"><FlaskConical size={17}/><div>Sandbox environment<small>Synthetic data clearly labeled</small></div><span className="dot amber"/></div><button className="help-button" onClick={()=>{setTab('methodology');setDrawer(null)}}><CircleHelp size={16}/> How the terminal works <ArrowUpRight size={14}/></button><div className="profile"><span className="profile-avatar">DE</span><div>Demo engineer<small>Local workspace</small></div><BadgeCheck size={16}/></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div><button className="mobile-menu icon-button" aria-label="Toggle navigation" onClick={()=>setMobileNav(!mobileNav)}><Menu size={18}/></button><span className="muted">Workspace</span><ChevronRight size={12}/><span>Commerce terminal</span><Badge tone="neutral">v1.0</Badge></div><div><span className={`dot ${health?'green-bg':'amber'}`}/><span className="connection-text">{health?'API connected':'Connecting to API'}</span><span className="topbar-divider"/><span className="mono timezone">NEW YORK / USD</span><button className="icon-button" aria-label="Open connections" onClick={()=>setDrawer('connections')}><Settings2 size={16}/></button></div></header>
      <main>
        <div className="page-heading"><div><div className="eyebrow"><span className="green">PRE-CHECKOUT GOVERNANCE</span><span>/</span> TERMINAL 001</div><h1>Quantitative Commerce Terminal<span className="heading-cursor"/></h1><p>Every purchase has a price. See the whole equation.</p></div><button className="button secondary export-button" disabled={!audit} onClick={download}><Download size={14}/> Export audit</button></div>
        <div className="scenario-bar"><div className="scenario-label"><FlaskConical size={14}/> DEMO SCENARIOS</div>{scenarios.map(s=><button key={s.id} disabled={busy} className={`scenario-button ${mandate.scenario===s.id?'selected':''}`} onClick={()=>selectScenario(s.id)}><s.icon size={14}/>{s.name}<span className={`dot ${s.id==='clean'?'green-bg':s.id==='anchor'?'amber':'red-bg'}`}/></button>)}<span className="scenario-note">Controlled storefront <ExternalLink size={11}/></span></div>
        {error&&<div className="error-banner" role="alert"><TriangleAlert size={16}/><span>{error}</span><button aria-label="Dismiss error" onClick={()=>setError('')}><X size={14}/></button></div>}
        <div className="experience-tabs"><button className={view==='terminal'?'active':''} onClick={()=>setView('terminal')}><ShieldCheck size={14}/>Audited checkout</button><button className={view==='discovery'?'active':''} onClick={()=>openDiscovery()}><Search size={14}/>Product discovery</button></div>
        {view==='discovery'?<ProductDiscovery initialUrl={discoveryUrl} onDeepAudit={deepAudit}/>:<div className="terminal-layout">
          <div className="analysis-column">
            <form className="url-bar" onSubmit={e=>{e.preventDefault();submitProduct()}}><Link2 size={16}/><input aria-label="Product URL" type="url" required value={mandate.product_url} onChange={e=>update('product_url',e.target.value)}/><button className="button primary" disabled={busy}>{busy?<LoaderCircle size={14} className="spin"/>:<ScanLine size={14}/>} {busy?`Auditing · ${elapsed}s`:isDemoProduct(mandate.product_url)?'Run audit':'Discover product'}<span className="keycap">↵</span></button></form>
            <div className="pipeline"><span><Check size={11}/> Buyer mandate</span><i/><span className={busy?'pulsing':''}>{busy?<LoaderCircle size={11} className="spin"/>:<Check size={11}/>} Collect evidence</span><i/><span><Check size={11}/> Quantitative synthesis</span><i/><span><LockKeyhole size={11}/> Govern settlement</span></div>
            <div className="metrics-grid">
              <div className="metric-card"><div className="metric-label">TOTAL FIAT EXPOSURE <Wallet size={13}/></div><div className="metric-value">{money(audit?.fiat.total)}<span>USD</span></div><div className="metric-foot"><span className={audit?.fiat.total==null?'muted':audit.fiat.total>mandate.max_spend?'red':'green'}><ArrowDownRight size={12}/>{audit?.fiat.total==null?'Total not evidenced':`${money(mandate.max_spend-audit.fiat.total)} headroom`}</span><span>cap {money(mandate.max_spend)}</span></div><div className="mini-track"><i style={{width:`${Math.min(100,(audit?.fiat.total??0)/Math.max(1,mandate.max_spend)*100)}%`}}/></div></div>
              <div className="metric-card"><div className="metric-label">OBSERVED MARKET MEDIAN <BarChart3 size={13}/></div><div className="metric-value">{money(audit?.market.median,audit?.market.currency)}<span>{audit?.market.currency==='UNKNOWN'?'':audit?.market.currency??'USD'}</span></div><div className="metric-foot"><span className="green">{audit?.market.sample_size??0} identical offers</span><span>item prices</span></div></div>
              <div className="metric-card"><div className="metric-label">GROSS CARBON FOOTPRINT <Leaf size={13}/></div><div className={`metric-value ${(gross??0)>mandate.purchase_carbon_cap?'red':''}`}>{num(gross)}<span>kg CO₂e</span></div><div className="metric-foot"><span className={gross==null?'muted':gross>mandate.purchase_carbon_cap?'red':'green'}>{gross==null?'Missing carbon evidence':gross>mandate.purchase_carbon_cap?'Above purchase cap':'Within purchase cap'}</span><span>cap {mandate.purchase_carbon_cap} kg</span></div><div className={`mini-track ${(gross??0)>mandate.purchase_carbon_cap?'danger-track':''}`}><i style={{width:`${Math.min(100,(gross??0)/Math.max(.01,mandate.purchase_carbon_cap)*100)}%`}}/></div></div>
              <div className="metric-card"><div className="metric-label">EVIDENCE SUPPORT INDEX <Sparkles size={13}/></div><div className="metric-value">{audit?.epistemic.score??'—'}<span>/ 100</span><div className="score-ticks">{Array.from({length:14},(_,i)=><i key={i} className={i<(audit?.epistemic.score??0)/100*14?'lit':''}/>)}</div></div><div className="metric-foot"><span className="blue">{audit?.epistemic.claims.length??0} claims assessed</span><span>see scoring</span></div></div>
            </div>
            <section className="product-strip"><div className="product-glyph"><Layers3 size={28} strokeWidth={1}/></div><div><div className="product-kicker">{audit?.product.sku??'AWAITING PRODUCT'} <span>•</span> {audit?.product.synthetic?'SYNTHETIC DEMO PRODUCT':'PRODUCT UNDER AUDIT'}</div><h2>{audit?.product.name??'Collecting your first evidence…'}</h2><p>{audit?.product.merchant??'Controlled storefront'} <span>·</span> {num(audit?.product.mass_kg)} kg <span>·</span> {audit?.product.origin??'Unknown origin'}</p></div><div className="product-status"><Badge tone={dirty?'amber':audit?.decision==='PASS'?'green':audit?.decision==='BLOCK'?'red':'amber'}>{dirty?'MANDATE CHANGED':audit?.decision??'PENDING'}</Badge><small>{audit?new Date(audit.created_at).toLocaleTimeString('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—'} ET</small></div></section>
            <div className="tab-bar"><button className={tab==='overview'?'active':''} onClick={()=>setTab('overview')}><Activity size={13}/> Audit overview</button><button className={tab==='evidence'?'active':''} onClick={()=>setTab('evidence')}><FileText size={13}/> Source evidence <span>{audit?.evidence.length??0}</span></button><button className={tab==='methodology'?'active':''} onClick={()=>setTab('methodology')}><Code2 size={13}/> Methodology</button><span className="tab-end"><span className="dot green-bg"/> {busy?'RUNNING':'DETERMINISTIC RULES'}</span></div>
            {tab==='overview'&&<>
              <section className="panel arbitrage-panel">
                <SectionTitle icon={BarChart3} title="Commodity arbitrage matrix" aside={<Badge tone={audit?.channel3.mode==='LIVE_API'?'green':'amber'}>{audit?.channel3.mode==='LIVE_API'?'CHANNEL3 LIVE':audit?.channel3.mode==='UNAVAILABLE'?'API UNAVAILABLE':'MOCK · SYNTHETIC'}</Badge>}/>
                <div className="market-summary">
                  <div><span>Original item price</span><strong>{money(audit?.market.original_price,audit?.market.currency)}</strong></div>
                  <div><span>Market median</span><strong>{money(audit?.market.median,audit?.market.currency)}</strong></div>
                  <div><span>Original vs. median</span><strong>{audit?.market.price_difference_pct==null?'—':`${audit.market.price_difference_pct>0?'+':''}${num(audit.market.price_difference_pct,1)}%`}</strong></div>
                  <div><span>Observed spread</span><strong>{money(audit?.market.spread,audit?.market.currency)}</strong></div>
                  <div><span>Reference deviation</span><strong className={audit?.market.suspicious_anchor?'amber-text':''}>{audit?.market.reference_deviation_pct==null?'—':`${audit.market.reference_deviation_pct>0?'+':''}${num(audit.market.reference_deviation_pct,1)}%`}</strong></div>
                  <div className="filter-tabs"><button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>All</button><button className={filter==='identical'?'active':''} onClick={()=>setFilter('identical')}>Exact</button><button className={filter==='equivalent'?'active':''} onClick={()=>setFilter('equivalent')}>Approximate</button><button className={filter==='unverified'?'active':''} onClick={()=>setFilter('unverified')}>Unverified</button></div>
                </div>
                <div className={`channel-status ${audit?.channel3.error_code?'has-error':''}`} data-testid="channel3-status">
                  <span>{audit?.channel3.mode==='LIVE_API'?'LIVE':'MOCK / UNAVAILABLE'} · HTTP {audit?.channel3.http_status??'—'} · {audit?.channel3.product_count??0} products · {audit?.channel3.offer_count??0} offers</span>
                  <p>{audit?.channel3.detail} {audit?.channel3.fallback_note}{audit?.channel3.partial?' Only resolved product offers are shown; comparable Search failed.':''}</p>
                  {audit?.channel3.retry_after_seconds!=null&&<p>Retry after {audit.channel3.retry_after_seconds} seconds.</p>}
                  {audit?.channel3.mode==='LIVE_API'&&!audit.market.sample_size&&<p>No verified identical-product offers for this audited item. A market median cannot be established from query similarity alone.</p>}
                </div>
                <div className="offers-grid"><AgGridReact<Offer> theme={gridTheme} rowData={offers} columnDefs={offerColumns} rowHeight={58} headerHeight={37} defaultColDef={{sortable:true,resizable:true}} domLayout="autoHeight" suppressCellFocus getRowId={p=>p.data.id} tooltipShowDelay={100} onRowClicked={event=>setSelectedOffer(event.data??null)}/></div>
                {selectedOffer&&offers.some(o=>o.id===selectedOffer.id)&&<div className="offer-detail"><button className="icon-button" aria-label="Close offer details" onClick={()=>setSelectedOffer(null)}><X size={13}/></button><h3>{selectedOffer.name}</h3><p>{selectedOffer.match_reason}</p><dl>{Object.entries(selectedOffer.specifications).filter(([,value])=>value!=null&&value!=='').map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value==='string'?value:JSON.stringify(value)}</dd></div>)}</dl><a className="text-link" href={selectedOffer.url} target="_blank" rel="noreferrer">View merchant product <ExternalLink size={11}/></a></div>}
                {!!audit?.market.alternatives.length&&<div className="alternative-list"><span className="tiny-label">TOP {audit.market.alternatives.length} LOWER-PRICE OPTIONS · ITEM PRICES</span>{audit.market.alternatives.map(offer=><div key={offer.id}><a href={offer.url} target="_blank" rel="noreferrer">{offer.merchant}<ExternalLink size={10}/></a><span>{offer.match==='identical'?'Exact product':'Approximate alternative'}</span><strong>{Number(offer.price).toFixed(2)} {offer.currency}</strong><button disabled={busy} onClick={()=>switchOffer(offer)}>Re-audit <ArrowUpRight size={11}/></button></div>)}</div>}
                <div className="panel-footnote"><CircleHelp size={12}/>{audit?.channel3.mode==='LIVE_API'?'Live catalog prices exclude unverified checkout costs.':'Mock rows are synthetic and do not represent Channel3 responses.'} Select a row for specifications. <a href={audit?.channel3.source} target="_blank" rel="noreferrer">API docs <ArrowUpRight size={10}/></a></div>
              </section>
              <div className="two-panels"><section className="panel persona-panel"><SectionTitle icon={ScanLine} title="Counterfactual price audit" aside={<span className="tiny-label">PAIRED SESSIONS</span>}/><div className="persona-prices"><div><span><span className="dot blue-bg"/> Clean session</span><strong>{money(audit?.persona.clean_price)}</strong><small>Fresh browser context</small></div><span className="versus">vs</span><div><span><span className="dot purple-bg"/> Personalized</span><strong>{money(audit?.persona.personalized_price)}</strong><small>Returning customer cookie</small></div></div><div className={`delta-bar ${audit?.persona.delta?'delta-warning':''}`}><span>Observed price difference</span><strong>{audit?.persona.delta==null?'NOT OBSERVED':`${audit.persona.delta>0?'+':''}${money(audit.persona.delta)}`}</strong></div><p className="microcopy">{audit?.persona.mode==='PLAYWRIGHT_DOM'?'Measured with isolated Playwright browser sessions. A controlled cookie experiment; no discrimination inference.':'Browser unavailable: fixture data only. No paired price observation asserted.'}</p></section>
              <section className="panel claims-panel"><SectionTitle icon={Sparkles} title="Epistemic claim audit" aside={<Badge tone={audit?.epistemic.mode==='LIVE_LLM'?'blue':'neutral'}>{audit?.epistemic.mode==='LIVE_LLM'?'LIVE LLM':'RULE FALLBACK'}</Badge>}/><div className="claims-list">{audit?.epistemic.claims.map((c,i)=><details className="claim-item" key={i}><summary><span className={`claim-icon ${c.verdict==='supported'?'green':c.verdict==='contradicted'?'red':'amber-text'}`}>{c.verdict==='supported'?<Check size={13}/>:<TriangleAlert size={12}/>}</span><span>{c.claim}</span><ChevronDown size={12}/></summary><p>{c.explanation}</p><button onClick={()=>setTab('evidence')}>Sources: {c.source_ids.join(', ')||'No corroborating evidence'} <ArrowUpRight size={10}/></button></details>)}</div><p className="microcopy">{audit?.epistemic.mode==='LIVE_LLM'?'Schema-validated output. All source IDs checked.':'Deterministic checks. Configure an LLM to enable model assessment.'}</p></section></div>
              <section className="panel carbon-panel"><SectionTitle icon={Leaf} title="Carbon accounting" aside={<Badge tone="neutral">GROSS EMISSIONS · 3 TIERS</Badge>}/><div className="carbon-content"><div className="carbon-breakdown"><div className="carbon-total">{num(gross)}<span>kg CO₂e</span><small>Total gross footprint</small></div><div className="carbon-stack">{[['Material',audit?.carbon.material_kg,'#6cd5b1'],['Fabrication',audit?.carbon.manufacturing_kg,'#7aa6ec'],['Shipping',audit?.carbon.shipping_kg,'#b399e5']].map(([label,value,color])=><div key={String(label)} style={{width:`${Math.max(2,(Number(value)||0)/Math.max(.001,gross??1)*100)}%`,background:String(color)}} title={`${label}: ${num(value as number)} kg`}/>)}</div><div className="carbon-legend">{[['Material',audit?.carbon.material_kg,'green-bg'],['Fabrication',audit?.carbon.manufacturing_kg,'blue-bg'],['Shipping',audit?.carbon.shipping_kg,'purple-bg']].map(([label,value,color])=><div key={String(label)}><span><i className={`dot ${color}`}/>{label}</span><strong>{num(value as number,3)} <small>kg</small></strong></div>)}</div></div><div className="carbon-month"><span className="tiny-label">MONTHLY CARBON LEDGER</span><div className="monthly-numbers"><strong>{num(monthlyUsed)}<small> / {mandate.monthly_carbon_cap} kg</small></strong><Badge tone="neutral">LOCAL DEMO LEDGER</Badge></div><div className="monthly-track"><i style={{width:`${Math.min(100,monthlyUsed/Math.max(1,mandate.monthly_carbon_cap)*100)}%`}}/><i className="projected" style={{width:`${Math.min(Math.max(0,100-monthlyUsed/Math.max(1,mandate.monthly_carbon_cap)*100),(gross??0)/Math.max(1,mandate.monthly_carbon_cap)*100)}%`}}/></div><div className="monthly-labels"><span><i className="dot green-bg"/> Settled</span><span><i className="dot projected-bg"/> This purchase</span><strong>{num(mandate.monthly_carbon_cap-monthlyUsed)} kg remaining</strong></div><div className="offset-summary"><Leaf size={15}/><div>Optional carbon contribution<small>{money(audit?.carbon.offset_amount)} · {audit?.carbon.offset_price_per_tonne??100} USD / tonne · SIMULATED</small></div><strong>0 kg<small>verified credit</small></strong></div></div></div><div className="panel-footnote"><CircleHelp size={12}/>Screening estimate with disclosed inputs. Offsets never reduce gross emissions or automatically clear a cap.<button onClick={()=>setTab('methodology')}>View factors <ArrowUpRight size={10}/></button></div></section>
            </>}
            {tab==='evidence'&&<section className="panel evidence-panel"><SectionTitle icon={FileText} title="Source evidence explorer" aside={<a className="text-link" href={audit?`/api/audits/${audit.id}/snapshot`:undefined} target="_blank" rel="noreferrer">Raw snapshot <ExternalLink size={12}/></a>}/><p className="panel-description">Untrusted merchant observations are preserved with selector, source URL, timestamp, and snapshot SHA-256. Export the audit for all provenance fields. Persona references begin with “p”.</p><div className="evidence-grid"><AgGridReact<Evidence> theme={gridTheme} rowData={audit?.evidence??[]} columnDefs={evidenceColumns} defaultColDef={{sortable:true,filter:true,resizable:true}} rowHeight={40} pagination paginationPageSize={15} paginationPageSizeSelector={[15,30,50]}/></div><div className="provenance-details"><p><strong>Source</strong> <a href={audit?.product.url} target="_blank" rel="noreferrer">{audit?.product.url}</a></p><p><strong>Captured</strong> {audit?.created_at}</p><p><strong>SHA-256</strong> <code>{audit?.evidence[0]?.sha256}</code></p><p><strong>Extractor</strong> {audit?.persona.mode}</p></div></section>}
            {tab==='methodology'&&<section className="panel methodology-panel"><SectionTitle icon={BookOpen} title="Reproducible methodology" aside={<Badge>VERSION 1.0</Badge>}/><article><h3>01 / Deterministic governance</h3><p>BLOCK takes priority over REVIEW, which takes priority over PASS. Only PASS permits settlement. Missing checkout totals, fee/subscription terms or critical carbon inputs block payment. Strict carbon caps always use gross emissions. A reviewable carbon exception requires the buyer’s explicit acknowledgement and recorded reason. LLM text cannot authorize payment.</p><h3>02 / Price comparisons</h3><p>{audit?.market.basis}</p><p>Reference prices more than 50% above the observed median are flagged for review. This is a heuristic, not evidence of deceptive pricing. Item prices cannot establish final checkout savings.</p><h3>03 / Evidence support index</h3><p>{audit?.epistemic.scoring}</p><p>{audit?.epistemic.uncertainty}</p><h3>04 / Counterfactual limitations</h3><p>{audit?.persona.limitations}</p><h3>05 / Carbon methodology & sources</h3><p>{audit?.carbon.methodology}</p>{audit?.carbon.factors.map((f,i)=><div className="factor-row" key={i}><div><strong>{f.name}</strong><span>{f.value??'MISSING'} {f.unit}</span></div><p>{f.boundary}</p><a href={f.source} target="_blank" rel="noreferrer">Published source / supplied fixture <ExternalLink size={11}/></a></div>)}<p>{audit?.carbon.uncertainty}</p><h3>06 / Settlement boundaries</h3><p>Orders v2 uses PayPal Sandbox only and only the controlled demo merchant. The carbon partner ({audit?.carbon.offset_partner}) is uncontracted; its proposed payment is SIMULATED at a configurable demo price of {money(audit?.carbon.offset_price_per_tonne)} per tonne. No funds transfer, verified removal, credit retirement, or atomic split is claimed. Only completed merchant captures enter the Sandbox ledger; explicitly simulated merchant entries are labeled SIMULATED.</p><p>Single-buyer local MVP, USD, one item per checkout. Storefront fixture inputs and fallback merchant offers are synthetic. External retailers require explicit host allowlisting and complete checkout evidence. No third-party merchant payment authority is assumed.</p></article></section>}
            <div className="analysis-footer"><span><ShieldCheck size={12}/> Evidence first. Buyer in control.</span><span className="mono">QCT ENGINE / 1.0.0 <span className="green">●</span></span></div>
          </div>
          <aside className="governance-column">
            <section className="panel mandate-panel" id="mandate-panel">
              <SectionTitle icon={SlidersHorizontal} title="Buyer mandate" aside={<LockKeyhole size={13}/>}/>
              <div className="mandate-fields">
                <span className="tiny-label">TRANSACTION LIMITS</span>
                <NumberField label="Maximum total spend" unit="USD" value={mandate.max_spend} onChange={v=>update('max_spend',v)}/>
                <div className="field-pair">
                  <NumberField label="Purchase carbon cap" unit="kg CO₂e" value={mandate.purchase_carbon_cap} onChange={v=>update('purchase_carbon_cap',v)}/>
                  <NumberField label="Monthly carbon cap" unit="kg CO₂e" value={mandate.monthly_carbon_cap} onChange={v=>update('monthly_carbon_cap',v)}/>
                </div>
                <NumberField label="Maximum checkout fees" unit="USD" value={mandate.max_fees} onChange={v=>update('max_fees',v)}/>
                <label className="text-field">Shipping destination<input value={mandate.destination} onChange={e=>update('destination',e.target.value)}/></label>
                <div className="mandate-separator"/><span className="tiny-label">BUYER PROTECTIONS</span>
                <Toggle label="No subscriptions" sub="Block recurring charges" checked={mandate.no_subscription} onChange={v=>update('no_subscription',v)}/>
                <Toggle label="Detect suspicious anchors" sub="Flag reference-price outliers" checked={mandate.detect_anchor} onChange={v=>update('detect_anchor',v)}/>
                <Toggle label="Carbon contribution" sub="Opt in to simulated partner leg" checked={mandate.offset_opt_in} onChange={v=>update('offset_opt_in',v)}/>
                <Toggle label="Live Channel3 discovery" sub="Off uses the reproducible demo catalog" checked={mandate.market_mode==='live'} onChange={v=>update('market_mode',v?'live':'synthetic')}/>
                {mandate.market_mode==='live'&&<label className="text-field">Comparable-product search query<input aria-label="Comparable-product search query" placeholder="Uses resolved product title when empty" value={mandate.market_query??''} onChange={e=>update('market_query',e.target.value)}/></label>}
                <label className="select-field">Carbon override policy<select value={mandate.override_policy} onChange={e=>{update('override_policy',e.target.value as Mandate['override_policy']);update('override_acknowledged',false)}}><option value="strict">Strict · no carbon overrides</option><option value="reviewable_carbon">Buyer may explicitly override carbon</option></select></label>
                {mandate.override_policy==='reviewable_carbon'&&<div className="override-fields"><label><input type="checkbox" checked={mandate.override_acknowledged} onChange={e=>update('override_acknowledged',e.target.checked)}/> I explicitly accept exceeding the carbon cap</label><textarea aria-label="Override reason" placeholder="Record why you accept the exception (10+ characters)" value={mandate.override_reason} onChange={e=>update('override_reason',e.target.value)}/></div>}
                <button className="cart-toggle" onClick={()=>setCartOpen(!cartOpen)}><Plus size={12}/> Optional merchant cart (JSON)<ChevronDown size={12}/></button>
                {cartOpen&&<textarea aria-label="Merchant cart JSON" placeholder={'[{"name":"Desk stand","quantity":1,"unit_price":68}]'} value={cartText} onChange={e=>{setCartText(e.target.value);setDirty(true);setApproved(false)}}/>}
                {dirty&&<button className="button apply-button" disabled={busy} onClick={submitProduct}><ScanLine size={13}/> Apply mandate & re-audit</button>}
              </div>
              <div className="mandate-foot"><LockKeyhole size={11}/> Enforced by the server before settlement</div>
            </section>
            <section className={`panel decision-panel ${audit?.decision?.toLowerCase()??''}`}><div className="decision-label">GOVERNANCE DECISION <ShieldCheck size={15}/></div><div className="decision-result">{busy?<LoaderCircle size={28} className="spin"/>:audit?.decision==='PASS'?<BadgeCheck size={30}/>:<ShieldCheck size={30}/>}<strong data-testid="decision">{busy?'AUDITING':dirty?'RE-AUDIT':audit?.decision??'PENDING'}</strong><span>{violations.length?`${violations.length} findings`:'Mandate check'}</span></div><p>{dirty?'Your mandate changed. Run a fresh audit before approval.':audit?.decision==='PASS'?'All strict mandates satisfied. Ready for buyer approval.':audit?.decision==='BLOCK'?'Settlement blocked. Resolve mandate violations and re-audit.':'Human review required before settlement.'}</p><div className="findings">{violations.map(f=><div key={f.code}><span className={`finding-dot ${f.severity==='BLOCK'?'red-bg':'amber'}`}/><div><strong>{f.code.replaceAll('_',' ')}</strong><p>{f.message}</p></div></div>)}{!violations.length&&audit&&<div className="all-checks"><Check size={13}/> Fiat, fees, subscriptions & carbon checked</div>}</div></section>
            <section className="panel settlement-panel">
              <SectionTitle icon={Wallet} title="Settlement" aside={<Badge tone="blue">SANDBOX</Badge>}/>
              <div className="ledger-rows"><div><span>Merchant payable</span><strong>{money(audit?.fiat.merchant_total)}</strong></div><div><span>Carbon leg <Badge>SIMULATED</Badge></span><strong>{money(audit?.fiat.offset)}</strong></div><div className="ledger-total"><span>Total fiat exposure</span><strong>{money(audit?.fiat.total)}</strong></div></div>
              <PayPalAuthCheck/>
              {order&&<div className="checkout-recovery" data-testid="checkout-recovery">
                <strong>Existing Sandbox checkout · {money(order.amount)}</strong>
                <p>PayPal status: <span className="mono">{order.paypal_status}</span></p>
                {!order.approval_verified&&!order.capture_completed&&<p>Not yet approved. Use a separate Personal Sandbox buyer account; the Business Sandbox account is the seller.</p>}
                {order.warning&&<p className="amber-text">{order.warning}</p>}
                {order.audit_expired&&!receipt&&<><p className="amber-text">The audit expired. Re-audit before starting a fresh checkout; this order is not being captured.</p><button onClick={()=>{window.history.replaceState({},'',location.pathname+'?new=1');runAudit(mandate)}} disabled={busy}>Re-audit for a fresh checkout <ArrowUpRight size={11}/></button></>}
                <button onClick={refreshCheckout} disabled={paymentBusy}>Refresh PayPal status <Activity size={11}/></button>
              </div>}
              <label className={`approval-check ${!pass||checkoutBlocked?'disabled':''}`}><input type="checkbox" checked={approved} disabled={!pass||checkoutBlocked||paymentBusy||!!receipt} onChange={e=>setApproved(e.target.checked)}/><span>I approve this audited purchase and its disclosed costs.</span></label>
              <button className="button paypal-button" disabled={!pass||checkoutBlocked||!approved||paymentBusy||!health?.paypal_configured||!sandboxEligible||!!receipt} onClick={payOrResume}>
                {paymentBusy?<LoaderCircle size={15} className="spin"/>:<LockKeyhole size={14}/>}
                {order?order.approval_verified?'Capture approved Sandbox order':'Resume PayPal approval':'Pay with PayPal Sandbox'}<ArrowRight size={14}/>
              </button>
              {!health?.paypal_configured&&<p className="credential-note">Add Sandbox credentials in .env to enable PayPal.</p>}
              <button className="simulate-button" disabled={!pass||!approved||paymentBusy||!!receipt||!!order} onClick={()=>settle('simulate')}><FlaskConical size={12}/> Simulate settlement · no money moves <ArrowUpRight size={12}/></button>
              <p className="settlement-note">Controlled demo merchant only. Carbon leg is separate and simulated; verified credit remains 0 kg.</p>
              {receipt&&<div className="receipt" role="status"><Check size={15}/><div><strong>{String(receipt.mode)} · {String(receipt.status)}</strong><p>{String(receipt.order_id)}</p><p>{receipt.mode==='SIMULATED'?'Local demo ledger updated. No PayPal call.':'PayPal confirmed capture. Sandbox ledger updated.'}</p></div></div>}
            </section>
          </aside>
        </div>}
      </main>
      <footer className="statusbar"><span><span className="dot green-bg"/> QCT TERMINAL <span className="muted">/</span> LOCAL WORKSPACE</span><span>Channel3: {audit?.channel3.mode??'—'}<span className="status-divider"/>Claims: {audit?.epistemic.mode??'—'}<span className="status-divider"/>PayPal: {health?.paypal_configured?'SANDBOX CONFIGURED':'UNCONFIGURED'}</span></footer>
    </div>
    {drawer&&<div className="drawer-backdrop" onClick={()=>setDrawer(null)}><section className="drawer" onClick={e=>e.stopPropagation()}><div className="drawer-heading"><h2>{drawer==='history'?'Audit history':'Adapter connections'}</h2><button className="icon-button" aria-label="Close panel" onClick={()=>setDrawer(null)}><X size={20}/></button></div>{drawer==='history'?<><p className="muted">Persisted in your local SQLite workspace.</p>{history.map(h=><button className="history-row" key={h.id} onClick={async()=>{const a=await api<Audit>('/api/audits/'+h.id);setAudit(a);setMandate(a.mandate);setDirty(false);setApproved(false);setReceipt(null);setOrder(null);setDrawer(null)}}><div><strong>{h.name}</strong><small>{new Date(h.created_at).toLocaleString('en-US',{timeZone:'America/New_York'})} ET</small></div><Badge tone={h.decision==='PASS'?'green':h.decision==='BLOCK'?'red':'amber'}>{h.decision}</Badge></button>)}{!history.length&&<p>No audits yet. Run an audit to collect evidence.</p>}</>:<><p className="muted">Keys are read from the server’s .env file. Restart FastAPI after changing configuration.</p>{[{name:'Channel3 / Product intelligence',ready:health?.channel3_configured,env:'CHANNEL3_API_KEY',detail:audit?.channel3.detail},{name:'LLM / Epistemic assessment',ready:health?.llm_configured,env:'LLM_API_KEY, LLM_BASE_URL, LLM_MODEL',detail:audit?.epistemic.detail},{name:'PayPal / Orders v2',ready:health?.paypal_configured,env:'PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET',detail:'Sandbox only. Create → buyer approval on PayPal → server-verified capture.'}].map(c=><div className="connection-card" key={c.name}><div><h3>{c.name}</h3><Badge tone={c.ready?'green':'amber'}>{c.ready?'CONFIGURED':'FALLBACK / UNCONFIGURED'}</Badge></div><code>{c.env}</code><p>{c.detail}</p></div>)}<div className="connection-card"><h3>Carbon partner / Separate leg</h3><Badge tone="amber">SIMULATED</Badge><p>No permissions or eligible partner accounts confirmed. Adapter records a proposal only, with zero verified carbon credit.</p></div><a className="text-link" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">FastAPI interactive API docs <ExternalLink size={13}/></a></>}</section></div>}
  </div>
}

function NumberField({label,unit,value,onChange}:{label:string;unit:string;value:number;onChange:(v:number)=>void}){return <label className="number-field">{label}<span><input aria-label={label} type="number" min="0" step="0.01" value={value} onChange={e=>onChange(Number(e.target.value))}/><small>{unit}</small></span></label>}
function Toggle({label,sub,checked,onChange}:{label:string;sub:string;checked:boolean;onChange:(v:boolean)=>void}){return <label className="toggle-row"><span>{label}<small>{sub}</small></span><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/><i className="toggle-track"/></label>}

function PayPalAuthCheck(){
  const [busy,setBusy]=useState(false);
  const [status,setStatus]=useState<{connected:boolean;http_status:number|null}|null>(null);
  const [error,setError]=useState(false);
  async function check(){setBusy(true);setError(false);try{setStatus(await api('/api/paypal/test-auth',{}))}catch{setError(true)}finally{setBusy(false)}}
  return <div className="auth-check"><button onClick={check} disabled={busy}>{busy?<LoaderCircle size={11} className="spin"/>:<Link2 size={11}/>} Test Sandbox connection</button>{status&&<span className={status.connected?'green':'amber-text'}>{status.connected?'Connected':'Not connected'} · HTTP {status.http_status??'unavailable'}</span>}{error&&<span className="red">Connection check unavailable</span>}</div>
}
