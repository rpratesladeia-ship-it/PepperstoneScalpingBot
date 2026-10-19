const express=require('express');
const app=express();
app.use(express.json({limit:'100kb'}));
const PORT=process.env.PORT||10000;
const KEY=(process.env.OPENAI_API_KEY||'').trim();
const MODEL=process.env.OPENAI_MODEL||'gpt-4.1-mini';
const TG_TOKEN=(process.env.TELEGRAM_BOT_TOKEN||'').trim();
const history=[];
const tg={offset:0,chatIds:new Set(),scanEnabled:false,asset:'BTCUSDT',interval:'5m',aiEnabled:true,lastScan:0,tradeAmountUsd:1,expiry:'5m',dailyLossLimitUsd:5,assetsMode:'all6'};
const ALLOWED=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT'];
const INTERVALS=['1m','3m','5m','15m'];
const EXPIRIES=['5s','10s','15s','30s','1m','3m','5m'];
app.get('/health',(req,res)=>res.json({status:'ok',mode:'demo-only',aiConfigured:!!KEY,telegramConfigured:!!TG_TOKEN,orderExecution:false}));
app.get('/api/status',(req,res)=>res.json({status:'online',mode:'demo-only',aiConfigured:!!KEY,telegramConfigured:!!TG_TOKEN,telegramScanEnabled:tg.scanEnabled,settings:{tradeAmountUsd:tg.tradeAmountUsd,expiry:tg.expiry,dailyLossLimitUsd:tg.dailyLossLimitUsd,assets:ALLOWED,interval:tg.interval},orderExecution:false,history:history.slice(0,20)}));
async function getCandles(symbol,interval){
 if(!ALLOWED.includes(symbol)||!INTERVALS.includes(interval))throw Error('Ativo ou período não permitido.');
 const response=await fetch('https://api.binance.com/api/v3/klines?symbol='+encodeURIComponent(symbol)+'&interval='+encodeURIComponent(interval)+'&limit=100',{headers:{'Accept':'application/json'},signal:AbortSignal.timeout(10000)});
 if(!response.ok)throw Error('Fonte de cotações indisponível.');
 const rows=await response.json();
 return rows.map(k=>({open:Number(k[1]),high:Number(k[2]),low:Number(k[3]),close:Number(k[4]),time:Number(k[0]),closed:Date.now()>=Number(k[6])})).filter(x=>x.closed);
}
async function analyzeCandles(c,asset,allowAI=true){
 if(!Array.isArray(c)||c.length<22)throw Error('São necessários pelo menos 22 candles fechados.');
 for(const x of c){for(const k of ['open','high','low','close'])if(!Number.isFinite(Number(x[k])))throw Error('Candles inválidos.');if(Number(x.high)<Math.max(Number(x.open),Number(x.close))||Number(x.low)>Math.min(Number(x.open),Number(x.close)))throw Error('OHLC inválido.');}
 const closes=c.map(x=>Number(x.close));
 function ema(a,p){const k=2/(p+1);let v=a[0];for(const x of a.slice(1))v=x*k+v*(1-k);return v;}
 const e9=ema(closes,9),e21=ema(closes,21),last=closes.slice(-15);
 const diffs=last.slice(1).map((x,i)=>x-last[i]);
 const gains=diffs.reduce((s,x)=>s+Math.max(0,x),0)/14,losses=diffs.reduce((s,x)=>s+Math.max(0,-x),0)/14;
 const rsi=losses===0?100:100-100/(1+gains/losses);
 const mom=(closes.at(-1)-closes.at(-4))/closes.at(-4)*100,body=Number(c.at(-1).close)-Number(c.at(-1).open);
 let side=e9>e21&&body>0&&mom>0?'CALL':e9<e21&&body<0&&mom<0?'PUT':'NO_TRADE';
 if((side==='CALL'&&rsi>=72)||(side==='PUT'&&rsi<=28))side='NO_TRADE';
 const result={asset,technicalSignal:side,finalSignal:'NO_TRADE',ema9:+e9.toFixed(6),ema21:+e21.toFixed(6),rsi:+rsi.toFixed(2),momentumPct:+mom.toFixed(4),aiApproved:false,aiReason:!KEY?'Chave da API de IA não configurada.':'IA não confirmou sinal.',createdAt:new Date().toISOString(),orderExecution:false,source:'Binance Spot'};
 if(KEY&&allowAI&&tg.aiEnabled&&side!=='NO_TRADE'){
  try{
   const response=await fetch('https://api.openai.com/v1/responses',{method:'POST',headers:{Authorization:'Bearer '+KEY,'Content-Type':'application/json'},body:JSON.stringify({model:MODEL,input:'Você é um filtro conservador para sinais de demonstração, não uma garantia. Avalie somente estes indicadores. Responda somente JSON com approved boolean e reason string. Em caso de dúvida, approved false. Dados: '+JSON.stringify(result),text:{format:{type:'json_object'}}}),signal:AbortSignal.timeout(15000)});
   if(response.ok){const data=await response.json();let out=data.output_text||'';if(!out)for(const item of(data.output||[]))for(const part of(item.content||[]))if(part.type==='output_text')out=part.text;const d=JSON.parse(out);result.aiApproved=d.approved===true;result.aiReason=String(d.reason||'Filtro IA').slice(0,250);if(result.aiApproved)result.finalSignal=side;}
   else result.aiReason='Falha na API de IA; sinal bloqueado.';
  }catch(e){result.aiReason='IA indisponível; sinal bloqueado.';}
 }
 history.unshift(result);history.splice(100);return result;
}
app.get('/api/market/candles',async(req,res)=>{
 try{const symbol=String(req.query.symbol||'BTCUSDT').toUpperCase(),interval=String(req.query.interval||'1m');if(!ALLOWED.includes(symbol))return res.status(400).json({error:'Ativo não permitido nesta fonte pública.'});if(!INTERVALS.includes(interval))return res.status(400).json({error:'Período inválido.'});const candles=await getCandles(symbol,interval);res.set('Cache-Control','no-store').json({source:'Binance Spot public API',symbol,interval,candles,warning:'Estas cotações não são da Pocket Option; OTC pode ter preços diferentes.'});}
 catch(e){res.status(502).json({error:'Não foi possível obter cotações públicas agora.'});}
});
app.post('/api/analyze',async(req,res)=>{try{const result=await analyzeCandles(req.body.candles,String(req.body.asset||'ativo não informado').slice(0,50));res.json(result);}catch(e){res.status(400).json({error:e.message||'Não foi possível analisar os candles.'});}});
async function tgSend(chatId,textMsg,keyboard){
 if(!TG_TOKEN)return;
 try{await fetch('https://api.telegram.org/bot'+TG_TOKEN+'/sendMessage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:chatId,text:textMsg,reply_markup:keyboard?{keyboard,resize_keyboard:true}:undefined}),signal:AbortSignal.timeout(10000)});}catch(e){console.error('Telegram send error:',e.message);}
}
function helpText(){return '🤖 NOSSO POCKET AI TRADER — DEMO\n\n/start — iniciar monitoramento\n/status — estado e configurações\n/scan — analisar todos os 6 ativos agora\n/monitorar — monitorar todos os ativos a cada minuto\n/parar — parar monitoramento\n/ativo BTCUSDT — escolher ativo individual\n/periodo 1m — gráfico: 1m, 3m, 5m ou 15m\n/expiracao 5m — duração desejada: 5s, 10s, 15s, 30s, 1m, 3m ou 5m\n/valor 1 — valor por entrada em US$ (0,01 a 1000)\n/ia on ou /ia off — filtro de IA\n/ativos — lista de ativos\n/ajuda — comandos\n\nConfiguração planejada: US$ 1 por operação, expiração 5m, limite diário US$ 5. Execução automática ainda não está conectada. Cotações Binance Spot podem diferir dos preços OTC.';}
async function doScan(chatId,auto=false){
 try{const candles=await getCandles(tg.asset,tg.interval);const d=await analyzeCandles(candles,tg.asset+' / '+tg.interval,true);const msg='📊 '+d.asset+'\nSinal técnico: '+d.technicalSignal+'\nSinal final: '+d.finalSignal+'\nRSI: '+d.rsi+' | Momentum: '+d.momentumPct+'%\nEMA 9: '+d.ema9+' | EMA 21: '+d.ema21+'\nIA aprova: '+d.aiApproved+'\nMotivo: '+d.aiReason+'\n\nFonte: Binance Spot. Não é cotação Pocket Option/OTC. Nenhuma ordem foi enviada.';await tgSend(chatId,msg);return d;}
 catch(e){await tgSend(chatId,'Não consegui analisar agora: '+e.message);return null;}
}
async function handleUpdate(update){
 const m=update.message;if(!m||!m.chat||typeof m.text!=='string')return;
 const chatId=m.chat.id,textMsg=m.text.trim(),parts=textMsg.split(/\s+/),cmd=parts[0].split('@')[0].toLowerCase().replace(/[.,!?;:]+$/,'');
 tg.chatIds.add(chatId);
 if(cmd==='/start'){await tgSend(chatId,'Bem-vindo ao NOSSO Pocket Demo Bot. Ele é independente do bot de terceiros. Começa em modo de sinais, sem execução de ordens.\n\n'+helpText(),[['📊 Analisar agora','⚙️ Estado','🛑 Parar monitoramento']]);return;}
 if(cmd==='/ajuda'||cmd==='/help'){await tgSend(chatId,helpText());return;}
 if(cmd==='/status'||textMsg==='⚙️ Estado'){await tgSend(chatId,'Estado: online\nModo: somente demo / sinais\nIA: '+(KEY?'chave configurada':'não configurada')+'; filtro '+(tg.aiEnabled?'ligado':'desligado')+'\nAtivos: '+ALLOWED.join(', ')+'\nGráfico: '+tg.interval+'\nValor por entrada: US$ '+tg.tradeAmountUsd.toFixed(2)+'\nExpiração desejada: '+tg.expiry+'\nLimite diário planejado: US$ '+tg.dailyLossLimitUsd+'\nMonitoramento: '+(tg.scanEnabled?'ligado':'desligado')+'\nExecução Pocket Option: NÃO implementada.');return;}
 if(cmd==='/ativos'){await tgSend(chatId,'Ativos disponíveis: '+ALLOWED.join(', ')+'\nUse /ativo BTCUSDT para escolher.');return;}
 if(cmd==='/ativo'){const a=(parts[1]||'').toUpperCase();if(!ALLOWED.includes(a)){await tgSend(chatId,'Ativo inválido. Use /ativos para ver a lista.');return;}tg.asset=a;await tgSend(chatId,'Ativo definido: '+a);return;}
 if(cmd==='/periodo'){const p=parts[1]||'';if(!INTERVALS.includes(p)){await tgSend(chatId,'Gráficos suportados pela fonte de dados atual: 1m, 3m, 5m ou 15m. Segundos não são suportados pela API de candles atual; não vou fingir que funcionam. Exemplo: /periodo 1m');return;}tg.interval=p;await tgSend(chatId,'Período do gráfico definido: '+p+'. Esse é o intervalo dos candles, não a expiração da operação.');return;}
 if(cmd==='/valor'){const raw=(parts[1]||'').replace(',','.');const amount=Number(raw);if(!Number.isFinite(amount)||amount<0.01||amount>1000){await tgSend(chatId,'Informe um valor entre US$ 0,01 e US$ 1000. Exemplo: /valor 1 ou /valor 2.50. Por enquanto é apenas configuração; não envia ordens.');return;}tg.tradeAmountUsd=Math.round(amount*100)/100;await tgSend(chatId,'Valor por entrada definido para US$ '+tg.tradeAmountUsd.toFixed(2)+'. Configuração salva apenas na memória desta execução; nenhuma ordem é enviada.');return;}
 if(cmd==='/expiracao'){const p=(parts[1]||'').toLowerCase();if(!EXPIRIES.includes(p)){await tgSend(chatId,'Expirações configuráveis: '+EXPIRIES.join(', ')+'. Exemplo: /expiracao 5m. É apenas uma preferência até existir execução Pocket Option validada.');return;}tg.expiry=p;await tgSend(chatId,'Expiração desejada definida: '+p+'. Ainda não é aplicada a uma ordem porque a execução Pocket Option não está conectada.');return;}
 if(cmd==='/ia'){const v=(parts[1]||'').toLowerCase();if(!['on','off'].includes(v)){await tgSend(chatId,'Use /ia on ou /ia off. É necessário configurar OPENAI_API_KEY no Render para usar a IA.');return;}tg.aiEnabled=v==='on';await tgSend(chatId,'Filtro de IA '+(tg.aiEnabled?'ligado':'desligado')+'. Chave configurada: '+(!!KEY)+'.');return;}
 if(cmd==='/scan'||textMsg==='📊 Analisar agora'){await doScan(chatId,false,true);return;}
 if(cmd==='/monitorar'){tg.scanEnabled=true;await tgSend(chatId,'Monitoramento ligado para os 6 ativos, a cada 60 segundos enquanto o serviço estiver ativo. Configuração planejada: US$ 1, expiração 5m, limite diário US$ 5. Isso ainda é monitoramento de sinais, não execução de ordens. Para parar, use /parar.');await doScan(chatId,false,true);return;}
 if(cmd==='/parar'||textMsg==='🛑 Parar monitoramento'){tg.scanEnabled=false;await tgSend(chatId,'Monitoramento pausado.');return;}
 await tgSend(chatId,'Não reconheci esse comando. Use /ajuda.');
}
async function telegramPoll(){
 if(!TG_TOKEN)return;
 while(true){
  try{
   const r=await fetch('https://api.telegram.org/bot'+TG_TOKEN+'/getUpdates?offset='+tg.offset+'&timeout=25',{signal:AbortSignal.timeout(35000)});
   if(!r.ok){await new Promise(ok=>setTimeout(ok,5000));continue;}
   const data=await r.json();if(data.ok&&Array.isArray(data.result)){for(const u of data.result){tg.offset=u.update_id+1;await handleUpdate(u);}}
  }catch(e){console.error('Telegram polling error:',e.message);await new Promise(ok=>setTimeout(ok,5000));}
 }
}
setInterval(async()=>{if(!tg.scanEnabled||!tg.chatIds.size||Date.now()-tg.lastScan<60000)return;tg.lastScan=Date.now();for(const id of tg.chatIds)await doScan(id,true,true);},5000);
app.use(express.static(__dirname+'/public'));
app.get('*',(req,res)=>res.sendFile(__dirname+'/public/index.html'));
app.listen(PORT,'0.0.0.0',()=>{console.log('Pocket demo dashboard listening on '+PORT);if(TG_TOKEN)telegramPoll();else console.log('Telegram bot disabled: set TELEGRAM_BOT_TOKEN in Render.');});
