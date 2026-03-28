import * as THREE from 'three';
import { input } from './input';

// Tuning constants — tweak to taste
const MAX_SPEED = 40;        // units/s
const ACCELERATION = 20;     // units/s²
const BRAKE_DECEL = 40;      // units/s²
const REVERSE_MAX = 12;      // units/s
const FRICTION = 8;          // passive decel units/s²
const STEER_SPEED = 2.5;     // rad/s at low speed
const MIN_STEER_SPEED_FACTOR = 0.4; // steering tightens at high speed

export class CarController {
  readonly mesh: THREE.Group;
  speed = 0;          // signed, forward is positive
  heading = 0;        // radians

  constructor(mesh: THREE.Group, initialHeading = 0) {
    this.mesh = mesh;
    this.heading = initialHeading;
  }

  get speedKmh(): number {
    return Math.abs(this.speed) * 3.6; // rough visual "km/h"
  }

  update(dt: number) {
    // --- Throttle / brake ---
    if (input.brake) {
      // Handbrake: always decelerates toward zero
      if (this.speed > 0) this.speed = Math.max(0, this.speed - BRAKE_DECEL * dt);
      else if (this.speed < 0) this.speed = Math.min(0, this.speed + BRAKE_DECEL * dt);
    } else if (input.forward) {
      this.speed = Math.min(MAX_SPEED, this.speed + ACCELERATION * dt);
    } else if (input.reverse) {
      this.speed = Math.max(-REVERSE_MAX, this.speed - ACCELERATION * dt);
    } else {
      // Coast / friction
      if (this.speed > 0) this.speed = Math.max(0, this.speed - FRICTION * dt);
      else if (this.speed < 0) this.speed = Math.min(0, this.speed + FRICTION * dt);
    }

    // --- Steering ---
    const absSpeed = Math.abs(this.speed);
    if (absSpeed > 0.5) {
      // Reduce steering at high speed
      const speedRatio = absSpeed / MAX_SPEED;
      const steerFactor = THREE.MathUtils.lerp(1, MIN_STEER_SPEED_FACTOR, speedRatio);
      const steer = STEER_SPEED * steerFactor * dt;
      const direction = this.speed >= 0 ? 1 : -1; // reverse steering when going backward

      if (input.left) this.heading += steer * direction;
      if (input.right) this.heading -= steer * direction;
    }

    // --- Apply movement ---
    const vx = Math.sin(this.heading) * this.speed * dt;
    const vz = Math.cos(this.heading) * this.speed * dt;
    this.mesh.position.x += vx;
    this.mesh.position.z += vz;
    this.mesh.rotation.y = this.heading;
  }
}
