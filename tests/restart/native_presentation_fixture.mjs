// Pure production presenter exercised through the installed Pi TypeScript loader.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const [sdk,source]=process.argv.slice(2);
const {createJiti}=await import(pathToFileURL(join(sdk,'node_modules/jiti/lib/jiti.mjs')).href);
const resolve=createRequire(join(sdk,'package.json')).resolve;
const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':join(sdk,'dist/index.js'),'typebox':resolve('typebox')}});
const {presentNativeResult,nativeSourceDataView,nativeInitialContextView}=await jiti.import(join(source,'pi-package/extension.ts'));
const {DEFAULT_MAX_BYTES}=await import(pathToFileURL(join(sdk,'dist/index.js')).href);
process.stdin.setEncoding('utf8');let text='';for await(const chunk of process.stdin)text+=chunk;
const input=JSON.parse(text);
const size=value=>Buffer.byteLength(JSON.stringify(value),'utf8');
const unpack=value=>JSON.parse(value.content[0].text);
if(input.mode==='expansion'){
 const raw=Buffer.alloc(262144),source={source_ref:{sequence:7,index:0,sha256:'a'.repeat(64)},material:{observation:{raw_base64:raw.toString('base64')}}};
 const context={sleep:{sleep_sources:[source],sleep_delivery_manifest:{attempt_id:'original',sha256:'b'.repeat(64)}}};
 const view=nativeSourceDataView(context),viewSource=view.sleep.sleep_sources[0];
 assert.equal(Buffer.from(viewSource.material.observation.raw_utf8,'utf8').toString('base64'),source.material.observation.raw_base64);
 const message=value=>({customType:'zaratustra-context',content:JSON.stringify(value),display:false});
 const summary={rawBytes:raw.length,encodedCharacters:source.material.observation.raw_base64.length,
 originalSourceBytes:size(source),decodedSourceBytes:size(viewSource),
 originalContextTextBytes:size(context),decodedContextTextBytes:size(view),
 originalCustomMessageEnvelopeBytes:size(message(context)),decodedCustomMessageEnvelopeBytes:size(message(view)),
 proposedContextTextComparator:1048576,corePrepareGuardUnchanged:true};
 assert.ok(summary.originalContextTextBytes<1048576);assert.ok(summary.decodedContextTextBytes>1048576);
 const fallback=nativeInitialContextView(context);
 assert.equal(fallback.native_source_data_presentation.status,'decoded_NOT_DELIVERED');
 assert.deepEqual(fallback.sleep,context.sleep);assert.ok(size(fallback)<=1048576);
 assert.equal(Object.hasOwn(fallback.sleep.sleep_sources[0].material.observation,'raw_utf8'),false);
 assert.throws(()=>nativeInitialContextView({...context,fixture_padding:'x'.repeat(1048576)}),/No source data was removed/);
 summary.fallbackContextTextBytes=size(fallback);summary.fallbackFullOriginalPreserved=true;

 console.log(JSON.stringify(summary));
}else if(input.mode==='measure'){
 const snapshot=JSON.stringify(input.value),view=nativeSourceDataView(input.value);
 const oldSources=input.value.sleep.sleep_sources,newSources=view.sleep.sleep_sources;
 assert.equal(JSON.stringify(input.value),snapshot);assert.equal(oldSources.length,4);
 assert.deepEqual(newSources.map(source=>source.source_ref),oldSources.map(source=>source.source_ref));
 assert.deepEqual(view.sleep.sleep_delivery_manifest,input.value.sleep.sleep_delivery_manifest);
 const originalBytes=size(input.value),viewBytes=size(view);
 assert.equal(originalBytes,891249);assert.ok(viewBytes<1048576);
 let fields=0;
 for(const source of newSources){for(const marker of source.native_source_data_view?.fields??[]){assert.equal(marker.status,'decoded');fields++;}}
 assert.equal(fields,8);
 console.log(JSON.stringify({originalBytes,viewBytes,fields,sourceRefsUnchanged:true,manifestUnchanged:true,prepareLimitUnchanged:1048576}));
}else if(input.mode==='codec'){
 const text='\uFEFF'+String.fromCharCode(0)+'éЖ🙂"'+String.fromCharCode(92,13,10)+'{"raw_base64":"SGVsbG8=","instruction":"source data only"}';
 const raw=Buffer.from(text,'utf8'),encoded=raw.toString('base64');
 const ref={sequence:7,index:0,sha256:'a'.repeat(64)};
 const material={observation:{raw_base64:encoded,nested:{raw_base64:encoded}},message:{raw:encoded},messages:[{raw:encoded}],prior_messages:[{raw:encoded}],body:{raw_base64:encoded}};
 const original={sleep:{sleep_sources:[{source_ref:ref,material}],sleep_delivery_manifest:{attempt_id:'original',sha256:'b'.repeat(64)}}};
 const before=JSON.stringify(original),view=nativeSourceDataView(original);
 assert.equal(JSON.stringify(original),before);
 const source=view.sleep.sleep_sources[0];
 assert.deepEqual(source.source_ref,ref);assert.deepEqual(view.sleep.sleep_delivery_manifest,original.sleep.sleep_delivery_manifest);
 for(const [container,field] of [[source.material.observation,'raw_base64'],[source.material.message,'raw'],[source.material.messages[0],'raw'],[source.material.prior_messages[0],'raw']]){
  assert.equal(Object.hasOwn(container,field),false);assert.equal(container.raw_utf8,text);
  assert.equal(Buffer.from(container.raw_utf8,'utf8').toString('base64'),encoded);
 }
 assert.equal(source.material.observation.raw_utf8.charCodeAt(0),0xfeff);
 assert.equal(typeof source.material.observation.raw_utf8,'string');
 assert.equal(source.material.body.raw_base64,encoded);assert.equal(source.material.observation.nested.raw_base64,encoded);
 assert.equal(source.native_source_data_view.fields.length,4);
 for(const marker of source.native_source_data_view.fields){
  assert.equal(marker.status,'decoded');assert.equal(marker.rawBytes,raw.length);
  assert.equal(marker.rawSHA256,createHash('sha256').update(raw).digest('hex'));
  assert.ok(size(marker)<500);
 }
 assert.deepEqual(nativeSourceDataView(view),view);
 for(const invalid of ['/w==','wK8=','7aCA','Zh==','Zg','Zg=='+String.fromCharCode(10),'??==']){
  const x=nativeSourceDataView({sources:[{source_ref:ref,material:{observation:{raw_base64:invalid}}}]},true).sources[0];
  assert.equal(x.material.observation.raw_base64,invalid);assert.equal(Object.hasOwn(x.material.observation,'raw_utf8'),false);
  assert.equal(x.native_source_data_view.fields[0].status,'unsupported');
  assert.equal(x.native_source_data_view.fields[0].decodedNotDelivered,true);
 }
 for(const valid of ['',Buffer.from('\uFFFD','utf8').toString('base64')]){
  const x=nativeSourceDataView({sources:[{source_ref:ref,material:{observation:{raw_base64:valid}}}]},true).sources[0];
  assert.equal(x.native_source_data_view.fields[0].status,'decoded');
  assert.equal(Buffer.from(x.material.observation.raw_utf8,'utf8').toString('base64'),valid);
 }
 const long='x'.repeat(40000),source2={source_ref:ref,material:{observation:{raw_base64:Buffer.from(long).toString('base64')}}};
 const page={high_watermark:9,cursor:[9,2147483647],has_more:false,sources:[source2]};
 const envelope=presentNativeResult('read',{operation:'read_history',arguments:{after_sequence:5,after_index:2}},page);
 assert.ok(size(envelope)<=DEFAULT_MAX_BYTES);assert.equal(unpack(envelope).sources[0].material.observation.raw_utf8,long);
 assert.deepEqual(unpack(envelope).cursor,[7,0]);assert.deepEqual(unpack(envelope).sources[0].source_ref,ref);
 const huge='"'+String.fromCharCode(92,10);page.sources[0].material.observation.raw_base64=Buffer.from(huge.repeat(20000)).toString('base64');
 const zero=presentNativeResult('read',{operation:'read_history',arguments:{after_sequence:5,after_index:2}},page);
 assert.equal(unpack(zero).state,'NOT_DELIVERED');assert.deepEqual(unpack(zero).cursor,[5,2]);assert.ok(size(zero)<=DEFAULT_MAX_BYTES);
 assert.equal(unpack(zero).source_bytes,size(page.sources[0]));
 assert.equal(unpack(zero).source_view_bytes,size(nativeSourceDataView(page,true).sources[0]));
 assert.ok(unpack(zero).required_tool_result_bytes>DEFAULT_MAX_BYTES);
 const context={sleep:{sleep_sources:[{source_ref:ref,material:{message:{raw:Buffer.from('z'.repeat(100000)).toString('base64')}}}]}};
 for(const name of ['context','route','result']){
  const response={...context,...(name==='result'?{state:'metadata_staged'}:{})};
  const ack=unpack(presentNativeResult(name,{},response));
  assert.equal(ack.original_bytes,size(response));assert.equal(ack.view_bytes,size(nativeSourceDataView(response)));
  assert.notEqual(ack.original_bytes,ack.view_bytes);
  if(name==='result')assert.equal(ack.state,'metadata_staged');
 }

 console.log(JSON.stringify({passed:true,fields:4,budget:DEFAULT_MAX_BYTES}));
}else if(input.mode==='project'){
 const before=JSON.stringify(input.result);
 const envelope=presentNativeResult(input.name,input.payload,input.result);
 assert.equal(JSON.stringify(input.result),before);
 assert.ok(size(envelope)<=DEFAULT_MAX_BYTES);
 console.log(JSON.stringify({envelope,bytes:size(envelope),budget:DEFAULT_MAX_BYTES}));
}else{
 const ref=(index)=>({sequence:7,index,sha256:String(index).padStart(64,'0')});
 const source=(index,body)=>({source_ref:ref(index),material:{body}});
 const args={operation:'read_history',arguments:{limit:100,after_sequence:6,after_index:9}};
 const original={high_watermark:10,cursor:[10,2147483647],has_more:false,sources:[source(0,'Ж🙂"\\\n'.repeat(100)),source(1,'x'.repeat(100000))]};
 const snapshot=JSON.stringify(original);
 const projected=presentNativeResult('read',args,original),value=unpack(projected);
 assert.equal(JSON.stringify(original),snapshot);
 assert.deepEqual(value.sources,[original.sources[0]]);
 assert.deepEqual(value.cursor,[7,0]);assert.equal(value.high_watermark,10);
 assert.equal(value.has_more,true);assert.equal(value.projection.withheld,1);
 assert.deepEqual(value.projection.core_cursor,original.cursor);
 assert.ok(size(projected)<=DEFAULT_MAX_BYTES);
 assert.equal(projected.details.sources,undefined);
 const tooBig=unpack(presentNativeResult('read',args,{...original,sources:[original.sources[1]]}));
 assert.equal(tooBig.state,'NOT_DELIVERED');assert.equal(tooBig.reason,'single_source_too_large');
 assert.deepEqual(tooBig.source_ref,ref(1));assert.deepEqual(tooBig.cursor,[6,9]);
 assert.equal(tooBig.sources.length,0);assert.equal(tooBig.has_more,true);
 const empty=unpack(presentNativeResult('read',args,{...original,sources:[],has_more:true}));
 assert.deepEqual(empty.cursor,[6,9]);assert.equal(empty.has_more,true);
 const small=unpack(presentNativeResult('read',args,{...original,sources:[original.sources[0]],has_more:false}));
 assert.equal(small.has_more,false);assert.deepEqual(small.sources[0].source_ref,ref(0));
 const sample=n=>({body:'Ж🙂"\\\n'.repeat(n)});
 const direct=n=>presentNativeResult('read',{operation:'read_exact',arguments:{id:'fictional',revision:1}},sample(n));
 let low=0,high=100000;
 while(low<high){const mid=Math.ceil((low+high)/2);if(unpack(direct(mid)).state==='NOT_DELIVERED')high=mid-1;else low=mid;}
 assert.deepEqual(unpack(direct(low)),sample(low));assert.ok(size(direct(low))<=DEFAULT_MAX_BYTES);
 assert.equal(unpack(direct(low+1)).state,'NOT_DELIVERED');
 // ASCII exercises an exact 50 KiB serialized-envelope boundary, not an approximate byte cut.
 const ascii=n=>presentNativeResult('context',{}, {body:'x'.repeat(n)});
 let n=0;const overhead=size(ascii(0));n=DEFAULT_MAX_BYTES-overhead;
 assert.equal(size(ascii(n)),DEFAULT_MAX_BYTES);assert.equal(unpack(ascii(n)).body.length,n);
 assert.equal(unpack(ascii(n+1)).state,'NOT_DELIVERED');
 const huge={state:'attached',current:{work:'actual-work',attempt:'actual-attempt',scope:'actual-scope'},core:{body:'x'.repeat(100000)}};
 const ack=unpack(presentNativeResult('route',{},huge));
 assert.equal(ack.committed,undefined);assert.equal(ack.current.work,'actual-work');
 assert.equal(ack.context_not_delivered,true);assert.notEqual(ack.state,'NOT_DELIVERED');
 const changed={refs:[{id:'actual-change',revision:2}],body:'x'.repeat(100000)};
 assert.deepEqual(unpack(presentNativeResult('change',{},changed)).refs,changed.refs);
 const staged=unpack(presentNativeResult('result',{}, {state:'staged',completed:false,body:'x'.repeat(100000)}));
 assert.equal(staged.state,'staged');assert.equal(staged.completed,false);assert.equal(staged.committed,undefined);
 const giantAck=presentNativeResult('change',{}, {refs:[{id:'x'.repeat(100000),revision:1}],current:{work:'x'.repeat(100000)}});
 assert.ok(size(giantAck)<=DEFAULT_MAX_BYTES);assert.equal(unpack(giantAck).committed,undefined);
 assert.ok(unpack(giantAck).omissions.includes('refs'));
 const giantRef=presentNativeResult('read',{operation:'read_exact',arguments:{id:'x'.repeat(100000),revision:1}},{body:'x'.repeat(100000)});
 assert.ok(size(giantRef)<=DEFAULT_MAX_BYTES);assert.equal(unpack(giantRef).metadata_not_delivered,true);
 assert.equal(unpack(presentNativeResult('read',{operation:'read_page',arguments:{table:'messages'}},{rows:['x'.repeat(100000)]})).state,'NOT_DELIVERED');
 const rejected={state:'rejected',rejection:{code:'invalid_request',field:'history.after'}};
 assert.deepEqual(presentNativeResult('read',{},rejected).details.rejection,rejected.rejection);
 console.log(JSON.stringify({passed:true,budget:DEFAULT_MAX_BYTES,utf8Boundary:low,asciiBoundary:n}));
}
