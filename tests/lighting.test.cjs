const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const layout = JSON.parse(fs.readFileSync(path.join(root, 'thingsboard/widgets/lighting-layout.json'), 'utf8'));
const controller = fs.readFileSync(path.join(root, 'thingsboard/widgets/classroom.js'), 'utf8');
const context = {self: {}};
vm.createContext(context);
vm.runInContext(controller, context);
assert.equal(layout.version, 4);
assert.equal(layout.orientation, 'transverse');
assert.equal(layout.coverage, 'full-scene');
assert.equal(layout.lanes.length, 4);
const polygons = layout.lanes.map(lane => context.coveragePolygon(layout,lane));
function contains(polygon, point) {
  return polygon.every((a,i) => {
    const b=polygon[(i+1)%polygon.length];
    return (b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]) >= -1e-10;
  });
}
for (let i=0;i<4;i++) {
  const lane=layout.lanes[i];
  assert.equal(lane.id,i+1);
  assert.deepEqual(lane.range,[i/4,(i+1)/4]);
  assert(lane.marker.every(x=>x>0 && x<1));
  assert(contains(polygons[i],lane.marker),'Each numbered marker must sit inside its own band');
  assert(contains(polygons[i],context.planePoint(layout.projectionQuad,.5,(i+.5)/4)));
  if(i) assert(lane.marker[1]>layout.lanes[i-1].marker[1]);
}
// Check the entire image, not merely a floor or desk quadrilateral.
for(let y=0;y<100;y++) for(let x=0;x<160;x++) {
  const p=[(x+.5)/160,(y+.5)/100];
  assert(polygons.some(poly=>contains(poly,p)),`unlit hole at ${p}`);
}
for(const p of layout.boardProbes) assert(contains(polygons[0],p),'Light 1 must cover every board panel');
for(let state=0;state<16;state++) {
  const enabled=layout.lanes.filter(lane=>state & (1<<(lane.id-1))).map(lane=>lane.id);
  const svg=context.lightingSvg(layout,enabled);
  assert.equal((svg.match(/<path /g)||[]).length,1,'use one union path, not alpha-stacked strips');
  assert.equal((svg.match(/ Z/g)||[]).length,enabled.length);
}
assert(!fs.readFileSync(path.join(root, 'thingsboard/widgets/classroom.css'), 'utf8').includes('radial-gradient'));
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex');
assert.equal(hash('assets/classroom-overview-v2.png'), hash('assets/previews/classroom-corner-v3.png'), 'asset must be the user-approved image');
assert.equal(layout.lanes[0].range[0], 0);
assert.equal(layout.lanes[3].range[1], 1);
assert(layout.lanes.every((lane, i) => !i || lane.marker[1] > layout.lanes[i-1].marker[1]), 'numbering must run from board to rear');
console.log('Lighting PASS: Light 1 covers the board; four adjoining transverse bands cover 100% of the approved scene without holes.');
