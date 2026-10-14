import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {syncBuiltinESMExports} from 'node:module';
import {Readable} from 'node:stream';
import {once} from 'node:events';
import {createGateway} from '../server/gateway.mjs';
import {pack,PreviewQueue,FRAME_HEADER_RESERVE} from '../src/protocol.ts';
import {startBatch} from '../src/batch.ts';
import {defaults} from '../src/settings.ts';
import type {Api} from '../src/api.ts';
test('Windows gateway static request uses Windows path containment',async()=>{
 const originals={resolve:path.resolve,relative:path.relative,isAbsolute:path.isAbsolute,existsSync:fs.existsSync,statSync:fs.statSync,createReadStream:fs.createReadStream};
 const root='C:\\controller\\dist';const asset=path.win32.join(root,'assets','app.js');
 Object.assign(path,{resolve:path.win32.resolve,relative:path.win32.relative,isAbsolute:path.win32.isAbsolute});Object.assign(fs,{existsSync:(p:unknown)=>p===asset,statSync:()=>({isFile:()=>true}),createReadStream:()=>Readable.from(['window.controller = true;'])});syncBuiltinESMExports();
 const gateway=createGateway({backends:['http://127.0.0.1:7860'],token:'test-token-at-least-24-characters',dist:root});
 try{gateway.listen(0,'127.0.0.1');await once(gateway,'listening');const r=await fetch(`http://127.0.0.1:${(gateway.address() as any).port}/assets/app.js`);assert.equal(r.status,200);assert.equal(await r.text(),'window.controller = true;');}
 finally{gateway.closeAllConnections();await new Promise<void>(resolve=>gateway.close(()=>resolve()));Object.assign(path,{resolve:originals.resolve,relative:originals.relative,isAbsolute:originals.isAbsolute});Object.assign(fs,{existsSync:originals.existsSync,statSync:originals.statSync,createReadStream:originals.createReadStream});syncBuiltinESMExports();}
});
test('missing or reset source sequence cannot freeze monotonic preview',()=>{
 const q=new PreviewQueue(0);const f=(seq:unknown,t:number)=>({meta:{seq,capture_monotonic:t},bytes:new Uint8Array([1])});q.enqueue(f(100,0),10);assert.equal(q.take(10)?.seq,100);q.enqueue(f(undefined,.1),10.1);assert.ok(q.take(10.1));q.enqueue(f(0,.2),10.2);assert.ok(q.take(10.2));q.enqueue(f(1,.3),10.3);assert.ok(q.take(10.3));
});
test('packing serializes each frame header only once',()=>{
 const original=JSON.stringify;let count=0;JSON.stringify=((...args:any[])=>{count++;return (original as any)(...args);}) as typeof JSON.stringify;
 try{pack([{meta:{seq:1},bytes:new Uint8Array([1])},{meta:{seq:2},bytes:new Uint8Array([2])}]);assert.equal(count,2);}finally{JSON.stringify=original;}
});
test('1000 pending cap applies when skip processed is disabled',async()=>{
 const p=structuredClone(defaults);p.photos.skip_processed=false;let uploads=0;
 const api={request:async()=>({web_capabilities:{relative_uploads:true,output_preflight:true,photo_options:true}}),upload:async()=>{uploads++;}} as unknown as Api;
 const files=Array.from({length:1001},(_,i)=>({name:`image${i}.webp`,webkitRelativePath:''} as File));
 await assert.rejects(()=>startBatch(api,p,'photos',files,undefined,new AbortController().signal,()=>{},()=>{}),/1000/);assert.equal(uploads,0);
});
test('cancelled upload cleans only its isolated unsubmitted batch',async()=>{
 const p=structuredClone(defaults);p.photos.skip_processed=false;const controller=new AbortController();const calls:{path:string;method:string}[]=[];let batchId='';
 const api={request:async(path:string,method='GET')=>{calls.push({path,method});return {web_capabilities:{relative_uploads:true,output_preflight:true,photo_options:true,batch_cleanup:true}};},upload:async(path:string)=>{batchId=new URL('http://test'+path).searchParams.get('batch_id')!;controller.abort();throw new DOMException('Cancelled','AbortError');}} as unknown as Api;
 await assert.rejects(()=>startBatch(api,p,'photos',[new File(['input'],'x.webp')],undefined,controller.signal,()=>{},()=>{}),{name:'AbortError'});
 assert.ok(calls.some(c=>c.method==='DELETE'&&c.path===`/upload/photos/batches/${batchId}`));assert.ok(!calls.some(c=>c.path==='/jobs/photos'));
});
test('lost submission response retains inputs for a possibly running job',async()=>{
 const p=structuredClone(defaults);p.photos.skip_processed=false;const calls:string[]=[];
 const api={request:async(path:string,method='GET')=>{calls.push(method+' '+path);if(path==='/health')return {web_capabilities:{relative_uploads:true,output_preflight:true,photo_options:true,batch_cleanup:true}};throw new Error('lost response');},upload:async(path:string)=>({input_dir:'/content/inputs/photos/batches/'+new URL('http://test'+path).searchParams.get('batch_id')})} as unknown as Api;
 await assert.rejects(()=>startBatch(api,p,'photos',[new File(['input'],'x.webp')],undefined,new AbortController().signal,()=>{},()=>{}),/lost response/);
 assert.ok(calls.includes('POST /jobs/photos'));assert.ok(!calls.some(c=>c.startsWith('DELETE ')));
});
test('preview jitter keeps the queue, a real epoch reset flushes it, and resent seq is dropped',()=>{
 const f=(seq:unknown,t:number)=>({meta:{seq,capture_monotonic:t},bytes:new Uint8Array([1])});
 const q=new PreviewQueue(5);q.enqueue(f(1,10),0);q.enqueue(f(2,10.1),0);q.enqueue(f(3,9.9),0);
 assert.equal(q.queue.length,3);
 q.enqueue(f(3,10.2),0);assert.equal(q.queue.length,3);assert.equal(q.dropped,1);
 q.enqueue(f(1,0.5),0);assert.equal(q.queue.length,1);
});
test('worst-case live frame header fits the batching reserve',()=>{
 const meta={seq:Number.MAX_SAFE_INTEGER,capture_monotonic:123456789.123456789,capture_time:1.7e9+0.123456789,send_time:1.7e9+0.123456789,codec:'image/webp',width:7680,height:4320};
 assert.ok(new TextEncoder().encode(JSON.stringify(meta)).length<FRAME_HEADER_RESERVE/2);
});
