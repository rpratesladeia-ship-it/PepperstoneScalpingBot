const express=require('express');
const app=express();
app.use(express.json({limit:'100kb'}));
const PORT=process.env.PORT||10000;
const KEY=(process.env.OPENAI_API_KEY||'').trim();
const MODEL=process.env.OPENAI_MODEL||'gpt-4.1-mini';
const history=[];
app.get('/health',(req,res)=>res.json({status:'ok',mode:'demo-only',aiConfigured:!!KEY,orderExecution:false}));
app.get('/api/status',(req,res)=>res.json({status:'online',mode:'demo-only',aiConfigured:!!KEY,orderExecution:false,history:history.slice(0,20)}));
app.get('/api/market/candles',async(req,res)=>{
 try{
  const allowed=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT'];
  const symbol=String(req.query.symbol||'BTCUSDT').toUpperCase();
  if(!allowed.includes(symbol))return res.status(400).json({error:'Ativo não permitido nesta fonte pública.'});
  const interval=String(req.query.interval||'1m');
  if(!['1m','3m','5m','15m'].includes(interval))return res.status(400).json({error:'Período inválido.'});
  const response=await fetch('https://api.binance.com/api/v3/klines?symbol='+encodeURIComponent(symbol)+'&interval='+encodeURIComponent(interval)+'&limit=100',{headers:{'Accept':'application/json'},signal:AbortSignal.timeout(10000)});
  if(!response.ok)return res.status(502).json({error:'Fonte de cotações indisponível.'});
  const rows=await response.json();
  const candles=rows.map(k=>({open:Number(k[1]),high:Number(k[2]),low:Number(k[3]),close:Number(k[4]),time:Number(k[0]),closed:Date.now()>=Number(k[6])}));
  res.set('Cache-Control','no-store').json({source:'Binance Spot public API',symbol,interval,candles,warning:'Essas cotações são da Binance Spot, não da Pocket Option; OTC e preços da corretora podem ser diferentes.'});
 }catch(e){res.status(502).json({error:'Não foi possível obter cotações públicas agora.'});}
});
app.post('/api/analyze',async(req,res)=>{
 try{
  const c=req.body.candles;
  if(!Array.isArray(c)||c.length<22) return res.status(400).json({error:'Envie pelo menos 22 candles OHLC reais.'});
  for(const x of c){for(const k of ['open','high','low','close'])if(!Number.isFinite(Number(x[k])))return res.status(400).json({error:'Candles inválidos.'}); if(Number(x.high)<Math.max(Number(x.open),Number(x.close))||Number(x.low)>Math.min(Number(x.open),Number(x.close)))return res.status(400).json({error:'OHLC inválido.'});}
  const closes=c.map(x=>Number(x.close));
  function ema(a,p){let k=2/(p+1),v=a[0];for(const x of a.slice(1))v=x*k+v*(1-k);return v;}
  const e9=ema(closes,9),e21=ema(closes,21);
  const diffs=closes.slice(-15).slice(1).map((x,i)=>x-closes.slice(-15)[i]);
  const gains=diffs.reduce((s,x)=>s+Math.max(0,x),0)/14,losses=diffs.reduce((s,x)=>s+Math.max(0,-x),0)/14;
  const rsi=losses===0?100:100-100/(1+gains/losses);
  const mom=(closes.at(-1)-closes.at(-4))/closes.at(-4)*100;
  const body=Number(c.at(-1).close)-Number(c.at(-1).open);
  let side=e9>e21&&body>0&&mom>0?'CALL':e9<e21&&body<0&&mom<0?'PUT':'NO_TRADE';
  if((side==='CALL'&&rsi>=72)||(side==='PUT'&&rsi<=28))side='NO_TRADE';
  const result={asset:String(req.body.asset||'ativo não informado').slice(0,30),technicalSignal:side,finalSignal:'NO_TRADE',ema9:+e9.toFixed(6),ema21:+e21.toFixed(6),rsi:+rsi.toFixed(2),momentumPct:+mom.toFixed(4),aiApproved:false,aiReason:'IA não configurada ou sinal técnico não confirmado.',createdAt:new Date().toISOString(),orderExecution:false};
  if(KEY&&side!=='NO_TRADE'){
   try{
    const response=await fetch('https://api.openai.com/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+KEY,'Content-Type':'application/json'},body:JSON.stringify({model:MODEL,input:'Filtro conservador para sinal de demonstração. Não afirme certeza. Retorne somente JSON {"approved":boolean,"reason":string}. Em caso de dúvida, approved false. Dados: '+JSON.stringify(result),text:{format:{type:'json_object'}}})});
    if(response.ok){const data=await response.json();let textOut=data.output_text||'';if(!textOut)for(const item of(data.output||[]))for(const part of(item.content||[]))if(part.type==='output_text')textOut=part.text;const d=JSON.parse(textOut);result.aiApproved=d.approved===true;result.aiReason=String(d.reason||'Filtro IA').slice(0,250);if(result.aiApproved)result.finalSignal=side;}
    else result.aiReason='A API de IA falhou; sinal bloqueado.';
   }catch(e){result.aiReason='IA indisponível; sinal bloqueado.';}
  }
  history.unshift(result);history.splice(20);res.json(result);
 }catch(e){res.status(400).json({error:'Não foi possível analisar os candles.'});}
});
app.use(express.static(__dirname+'/public'));
app.get('*',(req,res)=>res.sendFile(__dirname+'/public/index.html'));
app.listen(PORT,'0.0.0.0',()=>console.log('Pocket demo dashboard listening on '+PORT));
