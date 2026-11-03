import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText).toString('base64')}`;
const rational = moduleUrl(readFileSync(new URL('../src/lib/rational.ts',import.meta.url),'utf8').replace('import { tr } from "../i18n";','const tr = s => s;'));
const source = readFileSync(new URL('../src/lib/transcript.ts',import.meta.url),'utf8').replace('"./rational"',JSON.stringify(rational));
const { transcriptSelection, transcriptLockedTracks } = await import(moduleUrl(source));
const r = n => ({num:String(n),den:'2'});
const captions = [{id:'a',text:'你好',start:r(2),end:r(5)},{id:'b',text:'世界',start:r(4),end:r(8),words:[{text:'世',start:r(4),end:r(6)},{text:'界',start:r(6),end:r(8)}]}];
test('overlapping and adjacent selections merge once, without changing command identifiers',()=>{
 const choice=transcriptSelection(captions,{captionIds:['b','a','a'],captionId:'',wordIndices:[]});
 assert.deepEqual(choice.ranges,[{start:1,end:4}]); assert.equal(choice.duration,3);
 assert.deepEqual(choice.payload,{captionIds:['a','b']});
 const words=transcriptSelection(captions,{captionIds:[],captionId:'b',wordIndices:[1,0,1]});
 assert.deepEqual(words.ranges,[{start:2,end:4}]); assert.deepEqual(words.payload,{captionId:'b',wordIndices:[0,1]});
});
test('missing sentences, stale word indices, untimed words and invalid ranges cannot be previewed',()=>{
 for(const selection of [{captionIds:['missing'],captionId:'',wordIndices:[]},{captionIds:[],captionId:'b',wordIndices:[2]},{captionIds:[],captionId:'a',wordIndices:[0]},{captionIds:[],captionId:'b',wordIndices:[.5]},{captionIds:[],captionId:'',wordIndices:[]}]) assert.equal(transcriptSelection(captions,selection),null);
 assert.equal(transcriptSelection([{...captions[0],end:r(1)}],{captionIds:['a'],captionId:'',wordIndices:[]}),null);
});
test('selection fingerprint detects transcript timing or text drift but ignores unrelated captions',()=>{
 const selected={captionIds:['a'],captionId:'',wordIndices:[]}; const initial=transcriptSelection(captions,selected).signature;
 assert.notEqual(transcriptSelection([{...captions[0],text:'改字'},captions[1]],selected).signature,initial);
 assert.equal(transcriptSelection([captions[0],{...captions[1],text:'其他'}],selected).signature,initial);
});
test('ripple deletion protects a locked downstream track as well as overlap',()=>{
 const sequence={tracks:[{id:'before',locked:true,clips:[{timelineEnd:r(2)}]},{id:'after',locked:true,clips:[{timelineEnd:r(20)}]},{id:'open',clips:[{timelineEnd:r(20)}]}]};
 assert.deepEqual(transcriptLockedTracks(sequence,[{start:2,end:3}]).map(item=>item.id),['after']);
});
