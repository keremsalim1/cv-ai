import type { Transition } from 'motion/react'

/**
 * One spring family, three speeds. `visualDuration` is the time the motion
 * appears to take — the settle happens after it — which is what makes a spring
 * coordinate with time-based animation instead of fighting it.
 */
export const snap: Transition = { type: 'spring', visualDuration: 0.18, bounce: 0.15 }
export const flow: Transition = { type: 'spring', visualDuration: 0.28, bounce: 0.2 }
export const settle: Transition = { type: 'spring', visualDuration: 0.42, bounce: 0.18 }

/** Seconds between staggered children. */
export const STAGGER_STEP = 0.035

/**
 * A stagger is a rhythm, not a queue. Unbounded, a user with 200 applications
 * waits 7 seconds for the last row — so the delay stops growing after this many
 * items and everything past it arrives together.
 */
export const STAGGER_MAX_ITEMS = 12
