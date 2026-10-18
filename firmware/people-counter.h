#pragma once
#include <stdint.h>

// Hardware-independent algorithm. A is outside, B is inside. Both must overlap.
// Count only after 0 -> A -> AB -> B -> 0 (or its reverse). A retreat is not a visit.
class PeopleCounter {
 public:
  struct Snapshot {
    uint32_t occupancy = 0, entered = 0, exited = 0, errors = 0;
    bool uncertain = true;  // An empty room must be confirmed on first installation.
  } counts;
  enum Event { NONE, ENTERED, EXITED, REJECTED };

  PeopleCounter(uint32_t debounceMs = 30, uint32_t timeoutMs = 8000)
      : debounceMs_(debounceMs), timeoutMs_(timeoutMs) {}

  Event update(bool aBlocked, bool bBlocked, uint32_t now) {
    uint8_t raw = (aBlocked ? 1 : 0) | (bBlocked ? 2 : 0);
    if (raw != raw_) { raw_ = raw; changedAt_ = now; }
    if (phase_ && !rejected_ && uint32_t(now - startedAt_) >= timeoutMs_) {
      return reject();
    }
    if (raw_ == stable_ || uint32_t(now - changedAt_) < debounceMs_) return NONE;
    stable_ = raw_;
    if (rejected_) {
      if (!stable_) { rejected_ = false; phase_ = 0; }
      return NONE;
    }
    if (!phase_) {
      if (!stable_) return NONE;
      startedAt_ = now;
      if (stable_ == 3) return reject();  // Direction unknown; never guess.
      direction_ = stable_ == 1 ? 1 : -1;
      phase_ = 1;
      return NONE;
    }
    const uint8_t first = direction_ == 1 ? 1 : 2;
    const uint8_t last = direction_ == 1 ? 2 : 1;
    if (!stable_) {
      int completed = phase_ == 3 ? direction_ : 0;
      if (phase_ == 2) return reject();  // Both beams disappeared at once.
      phase_ = 0;
      if (!completed) return NONE;
      if (completed > 0) {
        ++counts.entered; ++counts.occupancy;
        return ENTERED;
      }
      ++counts.exited;
      if (counts.occupancy) --counts.occupancy;
      else { ++counts.errors; counts.uncertain = true; }
      return EXITED;
    }
    if (phase_ == 1 && stable_ == 3) phase_ = 2;
    else if (phase_ == 2 && stable_ == first) phase_ = 1;
    else if (phase_ == 2 && stable_ == last) phase_ = 3;
    else if (phase_ == 3 && stable_ == 3) phase_ = 2;
    else return reject();
    return NONE;
  }
  bool resetEmpty() {
    if (raw_ || stable_ || phase_ || rejected_) return false;
    counts = Snapshot{}; counts.uncertain = false;
    return true;
  }
  uint8_t blocked() const { return stable_; }
  const char* state() const {
    if (rejected_) return "BLOCKED";
    if (!phase_) return "IDLE";
    return direction_ > 0 ? "ENTERING" : "EXITING";
  }
 private:
  Event reject() {
    ++counts.errors; counts.uncertain = true;
    rejected_ = stable_ != 0 || raw_ != 0;
    phase_ = rejected_ ? 1 : 0;
    return REJECTED;
  }
  const uint32_t debounceMs_, timeoutMs_;
  uint32_t changedAt_ = 0, startedAt_ = 0;
  uint8_t raw_ = 0, stable_ = 0, phase_ = 0;
  int direction_ = 0;
  bool rejected_ = false;
};
