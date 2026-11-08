const fs=require('node:fs');
const path=require('node:path');
const root=process.argv[2]||process.cwd();
const file=path.join(root,'node_modules/@amazon-devices/keplerscript-commonmodules/index.js');
const before='return path.join(NODE_MODULES, `${libraryName}_${libraryVersion}`, moduleFilePath);';
const after='return path.posix.join(NODE_MODULES, `${libraryName}_${libraryVersion}`, moduleFilePath);';
const source=fs.readFileSync(file,'utf8');
if(source.includes(after))console.log('Windows portable module paths already patched.');
else {
 if(source.split(before).length!==2)throw Error('Unexpected upstream module-path implementation; manual review required.');
 fs.writeFileSync(file,source.replace(before,after));
 console.log('Patched the module-ID path calculation to use portable slash separators.');
}
