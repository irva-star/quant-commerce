import {useEffect,useMemo,useRef,useState} from 'react';
import {AgGridReact} from 'ag-grid-react';
import {themeQuartz,type ColDef,type ICellRendererParams} from 'ag-grid-community';
import {ArrowUpRight,ExternalLink,LoaderCircle,ScanLine,Search,ShieldCheck,TriangleAlert} from 'lucide-react';
import type {Offer} from './types';

interface Discovery {
  kind:'DISCOVERY';decision:'REVIEW';input_url:string;
  product:{id:string;title:string;materials?:string[]|string|null;key_features?:string[]|string|null}|null;
  products:unknown[];offers:Offer[];
  verification:{identity:string;checkout:string;carbon:string;purchase_authorized:false};
  provenance:{mode:string;provider:string;captured_at:string;synthetic:false;sources:{operation:string;http_status:number;source:string}[]};
  deep_audit:{allowed:boolean;reason:string};
  errors:{operation:string;error_code:string;detail:string;http_status:number|null;retry_after_seconds?:number|null}[];
}
const theme=themeQuartz.withParams({backgroundColor:'#10151c',foregroundColor:'#c3ccd8',headerBackgroundColor:'#141a22',borderColor:'#28333f',fontSize:12,fontFamily:'Inter,system-ui',wrapperBorder:false});
const text=(value:unknown)=>Array.isArray(value)?value.join(' · '):typeof value==='string'?value:'Not supplied';

export default function ProductDiscovery({initialUrl,onDeepAudit}:{initialUrl:string;onDeepAudit:(url:string)=>void}){
  const [url,setUrl]=useState(initialUrl),[query,setQuery]=useState('');
  const [result,setResult]=useState<Discovery|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [selected,setSelected]=useState<Offer|null>(null);
  const requested=useRef('');
  async function run(productUrl=url){
    setBusy(true);setError('');setResult(null);setSelected(null);
    try{
      const response=await fetch('/api/channel3/discover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:productUrl,query})});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Product URL was not accepted.');
      setResult(data);
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  useEffect(()=>{if(initialUrl&&requested.current!==initialUrl){requested.current=initialUrl;setUrl(initialUrl);run(initialUrl)}},[initialUrl]);
  const columns=useMemo<ColDef<Offer>[]>(()=>[
    {headerName:'PRODUCT',field:'name',minWidth:260,flex:2,tooltipField:'name'},
    {headerName:'MERCHANT',field:'merchant',minWidth:150,flex:1},
    {headerName:'ITEM PRICE',minWidth:140,flex:1,valueGetter:p=>p.data?`${Number(p.data.price).toFixed(2)} ${p.data.currency}`:'NOT VERIFIED',cellClass:'mono'},
    {headerName:'MATCH',field:'match',minWidth:140,valueFormatter:p=>p.value==='identical'?'Exact catalog product':p.value==='equivalent'?'Approximate alternative':'Unverified candidate'},
    {headerName:'PROVENANCE',width:120,valueGetter:()=> 'LIVE · Channel3'},
    {headerName:'MERCHANT LINK',minWidth:130,cellRenderer:({data}:ICellRendererParams<Offer>)=>data&&<a className="text-link" href={data.url} target="_blank" rel="noreferrer">Open merchant <ExternalLink size={12}/></a>},
  ],[]);
  return <section className="discovery-view" data-testid="discovery-view">
    <div className="panel"><div className="section-title"><h2><Search size={15}/>Live product discovery</h2><span className="badge blue">CATALOG RESEARCH</span></div>
      <p className="panel-description">Resolve a public product URL through Channel3. This action does not open a storefront browser or authorize a purchase.</p>
      <form className="discovery-form" onSubmit={event=>{event.preventDefault();run()}}>
        <label>Public product URL<input aria-label="Public product URL" required type="url" placeholder="https://merchant.example/products/item" value={url} onChange={event=>setUrl(event.target.value)}/></label>
        <label>Optional comparable-product query<input aria-label="Discovery search query" placeholder="Uses the resolved product title when available" value={query} onChange={event=>setQuery(event.target.value)}/></label>
        <button className="button primary" disabled={busy}>{busy?<LoaderCircle size={14} className="spin"/>:<Search size={14}/>} {busy?'Discovering…':'Discover product'}</button>
      </form>
    </div>
    {error&&<div className="error-banner" role="alert"><TriangleAlert size={15}/>{error}</div>}
    {result&&<>
      <section className="panel discovery-identity"><div><span className={`badge ${result.provenance.mode==='LIVE'?'green':'amber'}`}>{result.provenance.mode} · CHANNEL3</span><h2>{result.product?.title??'Product identity NOT VERIFIED'}</h2><a className="text-link" href={result.input_url} target="_blank" rel="noreferrer">Original product URL <ExternalLink size={12}/></a></div><div className="discovery-decision"><ShieldCheck size={24}/><strong>REVIEW</strong><small>Catalog evidence only</small></div>
        {result.product&&<dl><div><dt>Canonical catalog ID</dt><dd>{result.product.id}</dd></div><div><dt>Materials</dt><dd>{text(result.product.materials)}</dd></div><div><dt>Specifications</dt><dd>{text(result.product.key_features)}</dd></div></dl>}
      </section>
      <div className="discovery-verification"><div><span>Checkout total & recurring terms</span><strong>NOT VERIFIED</strong></div><div><span>Embodied & shipping carbon</span><strong>NOT VERIFIED</strong></div><div><span>Purchase authorization</span><strong>NONE</strong></div></div>
      <section className="panel"><div className="section-title"><h2>Market offers & source links</h2><span className="badge">{result.offers.length} OFFERS</span></div>
        <div className="channel-status"><span>Provider: {result.provenance.provider} · {result.provenance.mode} · synthetic: no</span><p>{result.provenance.sources.map(source=>`${source.operation} HTTP ${source.http_status}`).join(' · ')||'No live catalog evidence returned.'}</p><p>Captured {new Date(result.provenance.captured_at).toLocaleString('en-US',{timeZone:'America/New_York'})} ET. Prices are listing prices; shipping, tax, fees, currency conversion and pack/variant equivalence are not inferred.</p></div>
        <AgGridReact<Offer> theme={theme} rowData={result.offers} columnDefs={columns} domLayout="autoHeight" rowHeight={48} defaultColDef={{sortable:true,resizable:true}} getRowId={row=>row.data.id} onRowClicked={row=>setSelected(row.data??null)}/>
        {selected&&<div className="offer-detail"><h3>{selected.name}</h3><p>{selected.match_reason}</p><dl>{Object.entries(selected.specifications).filter(([,value])=>value!=null).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value==='string'?value:JSON.stringify(value)}</dd></div>)}</dl></div>}
        {!result.product&&<p className="panel-description">The original URL was not resolved by the provider. Any search results are candidates with unverified identity. You can enter a descriptive search query and try again.</p>}
        {result.errors.map((failure,index)=><div className="discovery-error" key={index}><strong>{failure.operation}: {failure.error_code} · HTTP {failure.http_status??'unavailable'}</strong><p>{failure.detail}</p>{failure.retry_after_seconds!=null&&<p>Retry after {failure.retry_after_seconds} seconds.</p>}</div>)}
      </section>
      <section className="panel discovery-deep"><div><h2><ScanLine size={16}/>Deep Storefront Audit</h2><p>{result.deep_audit.reason}</p><small>Runs Playwright and the existing mandate validator. Missing critical evidence continues to block payment.</small></div><button className="button secondary" disabled={!result.deep_audit.allowed||busy} onClick={()=>onDeepAudit(result.input_url)}>Deep Storefront Audit <ArrowUpRight size={13}/></button></section>
    </>}
  </section>
}
