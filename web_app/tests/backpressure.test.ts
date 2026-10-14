import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {WebSocket,WebSocketServer} from 'ws';
import {createGateway} from '../server/gateway.mjs';
test('a brief upstream write stall pauses and resumes relay without closing Live',async()=>{
 const upstream=http.createServer();upstream.listen(0,'127.0.0.1');await once(upstream,'listening');const target=`http://127.0.0.1:${(upstream.address() as any).port}`;
 const backend=new WebSocketServer({server:upstream});backend.on('connection',ws=>ws.on('message',(data,binary)=>ws.send(data,{binary})));
 const gateway=createGateway({backends:[target],token:'test-token-at-least-24-characters',origins:['https://controller.example']});gateway.listen(0,'127.0.0.1');await once(gateway,'listening');const base=`http://127.0.0.1:${(gateway.address() as any).port}`;
 const original=Object.getOwnPropertyDescriptor(WebSocket.prototype,'bufferedAmount')!;let stalled=true;let socket:WebSocket|undefined;
 Object.defineProperty(WebSocket.prototype,'bufferedAmount',{configurable:true,get(){return this.url===target.replace('http:','ws:')+'/ws/live'&&stalled?9*1024*1024:original.get!.call(this);}});
 try{const r=await fetch(base+'/gateway/ticket',{method:'POST',headers:{Authorization:'Bearer test-token-at-least-24-characters','Content-Type':'application/json',Origin:'https://controller.example'},body:JSON.stringify({path:'/ws/live'})});const {ticket}=await r.json();socket=new WebSocket(base.replace('http:','ws:')+'/ws/live?ticket='+ticket,{headers:{Origin:'https://controller.example'}});await once(socket,'open');
  const receive=()=>new Promise<any>((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('relay stalled permanently')),500);const message=(data:any,binary:boolean)=>{clean();resolve([data,binary]);};const closed=()=>{clean();reject(new Error('Live closed during brief write stall'));};const clean=()=>{clearTimeout(timer);socket!.off('message',message);socket!.off('close',closed);};socket!.once('message',message);socket!.once('close',closed);});
  let message=receive();socket.send(new Uint8Array([1,2,3]));let [bytes,binary]=await message;assert.equal(binary,true);assert.deepEqual(bytes,Buffer.from([1,2,3]));stalled=false;await new Promise(r=>setTimeout(r,60));assert.equal(socket.readyState,WebSocket.OPEN);message=receive();socket.send('after-stall');const [text,flag]=await message;assert.equal(flag,false);assert.equal(text.toString(),'after-stall');
 }finally{Object.defineProperty(WebSocket.prototype,'bufferedAmount',original);socket?.terminate();gateway.closeAllConnections();await new Promise<void>(r=>gateway.close(()=>r()));backend.clients.forEach(ws=>ws.terminate());await new Promise<void>(r=>backend.close(()=>r()));await new Promise<void>(r=>upstream.close(()=>r()));}
});
