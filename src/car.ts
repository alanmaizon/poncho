import * as THREE from 'three';
import { input } from './input';

// Tuning constants
const MAX_SPEED = 40;
const ACCELERATION = 20;
const BRAKE_DECEL = 40;
const REVERSE_MAX = 12;
const FRICTION = 8;
const STEER_SPEED = 2.5;
const MIN_STEER_SPEED_FACTOR = 0.4;

// Ground-follow
const GROUND_RAY_HEIGHT = 50;   // cast from this height above car
const GROUND_SMOOTHING = 12;    // higher = snappier ground follow

export class CarController {
  readonly mesh: THREE.Group;
  speed = 0;
  heading = 0;

  private raycaster = new THREE.Raycaster();
  private roadMesh: THREE.Mesh | null = null;
  private targetY = 0;

  constructor(mesh: THREE.Group, initialHeading = 0, roadMesh: THREE.Mesh | null = null) {
    this.mesh = mesh;
    this.heading = initialHeading;
    this.roadMesh = roadMesh;
    this.targetY = mesh.position.y;
  }

  get speedKmh(): number {
    return Math.abs(this.speed) * 3.6;
  }

  update(dt: number) {
    // --- Throttle / brake ---
    if (input.brake) {
      if (this.speed > 0) this.speed = Math.max(0, this.speed - BRAKE_DECEL * dt);
      else if (this.speed < 0) this.speed = Math.min(0, this.speed + BRAKE_DECEL * dt);
    } else if (input.forward) {
      this.speed = Math.min(MAX_SPEED, this.speed + ACCELERATION * dt);
    } else if (input.reverse) {
      this.speed = Math.max(-REVERSE_MAX, this.speed - ACCELERATION * dt);
    } else {
      if (this.speed > 0) this.speed = Math.max(0, this.speed - FRICTION * dt);
      else if (this.speed < 0) this.speed = Math.min(0, this.speed + FRICTION * dt);
    }

    // --- Steering ---
    const absSpeed = Math.abs(this.speed);
    if (absSpeed > 0.5) {
      const speedRatio = absSpeed / MAX_SPEED;
      const steerFactor = THREE.MathUtils.lerp(1, MIN_STEER_SPEED_FACTOR, speedRatio);
      const steer = STEER_SPEED * steerFactor * dt;
      const direction = this.speed >= 0 ? 1 : -1;
      if (input.left) this.heading += steer * direction;
      if (input.right) this.heading -= steer * direction;
    }

    // --- Apply XZ movement ---
    this.mesh.position.x += Math.sin(this.heading) * this.speed * dt;
    this.mesh.position.z += Math.cos(this.heading) * this.speed * dt;
    this.mesh.rotation.y = this.heading;

    // --- Ground follow: raycast down onto the Road mesh ---
    if (this.roadMesh) {
      const pos = this.mesh.position;
      const origin = new THREE.Vector3(pos.x, pos.y + GROUND_RAY_HEIGHT, pos.z);
      const down = new THREE.Vector3(0, -1, 0);

      this.raycaster.set(origin, down);
      this.raycaster.far = GROUND_RAY_HEIGHT * 2;

      const hits = this.raycaster.intersectObject(this.roadMesh, false);
      if (hits.length > 0) {
        // At the figure-8 crossing, the downward ray can hit both road levels.
        // Follow the surface nearest to the car's current elevation instead.
        const nearestSurface = hits.reduce((best, hit) => {
          const bestDelta = Math.abs(best.point.y - pos.y);
          const hitDelta = Math.abs(hit.point.y - pos.y);
          return hitDelta < bestDelta ? hit : best;
        });
        this.targetY = nearestSurface.point.y;
      }

      // Smooth interpolation to target height
      const t = 1 - Math.exp(-GROUND_SMOOTHING * dt);
      pos.y = THREE.MathUtils.lerp(pos.y, this.targetY, t);
    }
  }
}
