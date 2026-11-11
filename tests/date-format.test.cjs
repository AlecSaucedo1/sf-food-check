// Exercise the actual date formatter from app.js without loading the browser UI.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8');
const begin=source.indexOf('function fmt(');
const end=source.indexOf('const cls=',begin);
assert.ok(begin>=0&&end>begin,'Date formatter must be present in app.js');
const scope=vm.createContext({Intl, Date, Number});
vm.runInContext(source.slice(begin,end),scope);
const fmt=value=>vm.runInContext('fmt(value)',vm.createContext({...scope,value}));
const expected='Unknown date';
for(const invalid of [undefined,null,'','   ','NaN','Not a Date','N/A','2026-02-30','2026-02-29','2026-13-01','2026-00-10','2026-11-00','999999999999','2026-11-10T12:00:00T12:00:00']){
  assert.equal(fmt(invalid),expected,'Invalid date must not throw: '+String(invalid));
}
for(const [value,display] of [
  ['2026-11-10','Nov 10, 2026'],
  ['2026-11-10T00:00:00','Nov 10, 2026'],
  ['2026-11-10T00:00:00.000','Nov 10, 2026'],
  ['2024-02-29','Feb 29, 2024'],
  ['2019-01-01','Jan 1, 2019']
]){
  assert.equal(fmt(value),display,'Date mismatch: '+value);
}
console.log('Date-format regression tests passed');
