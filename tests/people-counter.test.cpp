#include "../firmware/people-counter.h"
#include <assert.h>
#include <iostream>
#include <initializer_list>
using C = PeopleCounter;
uint32_t now = 0;
C::Event stable(C& c, int mask, uint32_t hold = 40) {
  c.update(mask & 1, mask & 2, now);
  now += hold;
  return c.update(mask & 1, mask & 2, now);
}
void path(C& c, std::initializer_list<int> masks) { for (int mask : masks) stable(c, mask); }
int main() {
  C c;
  assert(c.counts.uncertain && c.resetEmpty() && !c.counts.uncertain);
  path(c,{1,3,2}); assert(c.counts.occupancy == 0); // Not counted until fully clear.
  assert(stable(c,0) == C::ENTERED);
  assert(c.counts.occupancy == 1 && c.counts.entered == 1);
  path(c,{2,3,1}); assert(stable(c,0) == C::EXITED);
  assert(c.counts.occupancy == 0 && c.counts.exited == 1);
  path(c,{1,0, 2,0, 1,3,1,0, 2,3,2,0}); // Step in then retreat.
  assert(c.counts.entered == 1 && c.counts.exited == 1);
  path(c,{1,3,2,3,1,0}); // Full retreat through both beams.
  assert(c.counts.occupancy == 0 && c.counts.entered == 1);
  path(c,{1,3,2,3,2,0}); // Hesitate but complete.
  assert(c.counts.occupancy == 1 && c.counts.entered == 2);
  for (int i=0;i<20;++i) path(c,{1,3,2,0});
  for (int i=0;i<21;++i) path(c,{2,3,1,0});
  assert(c.counts.occupancy == 0 && c.counts.entered == 22 && c.counts.exited == 22);
  path(c,{2,3,1,0}); // Never underflow; flag unknown starting occupancy.
  assert(c.counts.occupancy == 0 && c.counts.errors == 1 && c.counts.uncertain);
  assert(c.resetEmpty());
  path(c,{3}); assert(c.counts.errors == 1 && !c.resetEmpty());
  path(c,{1,0}); assert(c.counts.occupancy == 0 && c.resetEmpty());
  path(c,{1,2,0}); // Skipped overlap: reject rather than guess direction.
  assert(c.counts.occupancy == 0 && c.counts.errors == 1 && c.resetEmpty());
  path(c,{1,3,0}); assert(c.counts.occupancy == 0 && c.counts.errors == 1);
  assert(c.resetEmpty());
  stable(c,1); now += 8100;
  assert(c.update(true,false,now) == C::REJECTED);
  for(int i=0;i<100;++i) { now+=100; c.update(true,false,now); }
  assert(c.counts.errors == 1 && !c.resetEmpty()); // One error per obstruction.
  stable(c,0); assert(c.resetEmpty());
  // Contact bounce (<30 ms) does not create extra edges.
  for(int mask : {1,3,2,0}) {
    c.update(mask&1,mask&2,now);now+=5;
    c.update(false,false,now);now+=5;
    stable(c,mask);
  }
  assert(c.counts.entered == 1 && c.counts.occupancy == 1);
  // Correct unsigned arithmetic across millis() wrap.
  C wrap; now=0xfffffff0; path(wrap,{1,3,2,0});
  assert(wrap.counts.entered == 1);
  // Restoring the persisted snapshot retains occupancy / calibration.
  C restored; restored.counts=c.counts;
  assert(restored.counts.occupancy == 1 && !restored.counts.uncertain);
  std::cout << "PASS: entry/exit, completion, retreats, hesitation, repeated crossings, zero clamp, ambiguous start, invalid order, timeout, debounce, millis wrap, snapshot\n";
}
