import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const work=path.join(root,'artifacts',`selftest-${Date.now()}-${process.pid}`);
const args=[path.join(root,'skills/xhs-minitool-release/scripts/test_release.py'),'--work',work,'--project',process.env.PLAYWRIGHT_PROJECT||root];
if(process.env.PLAYWRIGHT_CHANNEL)args.push('--channel',process.env.PLAYWRIGHT_CHANNEL);
const result=spawnSync(process.env.PYTHON||(process.platform==='win32'?'python':'python3'),args,{cwd:root,stdio:'inherit',env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
if(result.error){console.error(result.error.message);process.exitCode=1;}else process.exitCode=result.status??1;
