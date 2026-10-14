import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import fs from 'node:fs';import path from 'node:path';
const require=createRequire(import.meta.url);fs.mkdirSync('work',{recursive:true});
const directory=fs.mkdtempSync(path.resolve('work/management-test-'));
const env={...process.env,PINBOARD_TEST_MODE:'1',PINBOARD_DATA_DIR:directory};delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(require('electron'),[path.resolve('scripts/management-smoke.cjs')],{env,stdio:'inherit'});
const timer=setTimeout(()=>child.kill(),60000);const status=await new Promise(resolve=>child.once('exit',resolve));clearTimeout(timer);
if(status!==0)throw Error(`Management UI failed: ${status}`);console.log(directory);
